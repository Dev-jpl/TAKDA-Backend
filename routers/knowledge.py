from fastapi import APIRouter, UploadFile, File, HTTPException, Header, Form, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import os

from database import supabase
from services.embeddings import process_document, embed_text
from services.ai import chat_with_documents

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class URLRequest(BaseModel):
    url: str
    title: Optional[str] = None
    user_id: str
    hub_id: Optional[str] = None


class ChatRequest(BaseModel):
    query: str
    user_id: str
    hub_id: Optional[str] = None
    document_ids: Optional[list[str]] = None


class DocumentCreate(BaseModel):
    title: str
    source_type: str
    raw_content: str
    source_url: Optional[str] = None
    user_id: str
    hub_id: Optional[str] = None


# --- Upload PDF ---
@router.post("/upload/pdf")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Form(...),
    hub_id: Optional[str] = Form(None),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    # Normalize empty-string to None
    if not hub_id or hub_id == "":
        hub_id = None

    content = await file.read()

    try:
        text = extract_pdf_text(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF extraction failed: {str(e)}")

    doc = supabase.table("documents").insert({
        "user_id": user_id,
        "hub_id": hub_id,
        "title": file.filename.replace(".pdf", ""),
        "source_type": "pdf",
        "raw_content": text,
    }).execute()

    document_id = doc.data[0]["id"]

    # Process embeddings in background to avoid timeouts
    background_tasks.add_task(process_document, document_id, text)

    return {
        "document_id": document_id,
        "title": file.filename,
        "processing": True,
        "message": "Project indexing started in background."
    }


# --- Upload URL ---
@router.post("/upload/url")
async def upload_url(body: URLRequest, background_tasks: BackgroundTasks):
    try:
        text, page_title = await extract_url_text(body.url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"URL extraction failed: {str(e)}")

    title = body.title or page_title or "Untitled"

    doc = supabase.table("documents").insert({
        "user_id": body.user_id,
        "hub_id": body.hub_id,
        "title": title,
        "source_type": "url",
        "source_url": body.url,
        "raw_content": text,
    }).execute()

    document_id = doc.data[0]["id"]

    background_tasks.add_task(process_document, document_id, text)

    return {
        "document_id": document_id,
        "title": title,
        "processing": True,
        "message": "Resource indexing started in background."
    }


# --- Get all documents ---
@router.get("/documents/{user_id}")
async def get_documents(user_id: str, hub_id: Optional[str] = None):
    query = supabase.table("documents") \
        .select("id, title, source_type, source_url, created_at") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True)

    if hub_id:
        query = query.eq("hub_id", hub_id)

    docs = query.execute()
    return docs.data


# --- Upload plain text / markdown ---
@router.post("/upload/text")
async def upload_text(body: DocumentCreate):
    doc = supabase.table("documents").insert({
        "user_id": body.user_id,
        "hub_id": body.hub_id,
        "title": body.title,
        "source_type": body.source_type,
        "raw_content": body.raw_content,
    }).execute()

    document_id = doc.data[0]["id"]

    await process_document(document_id, body.raw_content)

    return {
        "document_id": document_id,
        "title": body.title,
        "chunks_processed": True,
    }


# --- Delete document ---
@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    supabase.table("document_chunks") \
        .delete() \
        .eq("document_id", document_id) \
        .execute()

    supabase.table("documents") \
        .delete() \
        .eq("id", document_id) \
        .execute()

    return {"deleted": True}


# --- AI Chat ---
@router.post("/chat")
async def chat(body: ChatRequest):
    # Fetch document IDs for the hub if space is scoped
    doc_ids = body.document_ids or []
    
    if not doc_ids and body.hub_id:
        hubs_res = supabase.table("documents") \
            .select("id") \
            .eq("hub_id", body.hub_id) \
            .execute()
        doc_ids = [d["id"] for d in hubs_res.data]
        
    if not doc_ids and not body.hub_id:
        # Fallback for old global-space documents
        global_res = supabase.table("documents") \
            .select("id") \
            .eq("user_id", body.user_id) \
            .is_("hub_id", "null") \
            .execute()
        doc_ids = [d["id"] for d in global_res.data]

    if not doc_ids:
        return {
            "answer": "No relevant documents found. Please upload a source to this Hub or Space first.",
            "citations": [],
        }

    response = await chat_with_documents(
        query=body.query,
        user_id=body.user_id,
        hub_id=body.hub_id,
        document_ids=doc_ids,
    )
    return response


# --- Helpers ---
def extract_pdf_text(content: bytes) -> str:
    import PyPDF2
    import io
    reader = PyPDF2.PdfReader(io.BytesIO(content))
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text.strip()


async def extract_url_text(url: str) -> tuple[str, str]:
    import httpx
    from bs4 import BeautifulSoup

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, follow_redirects=True)
        soup = BeautifulSoup(response.text, "html.parser")

        page_title = ""
        if soup.title and soup.title.string:
            page_title = soup.title.string.strip()
        elif soup.find("h1"):
            page_title = soup.find("h1").get_text(strip=True)
        else:
            slug = url.rstrip("/").split("/")[-1]
            page_title = slug.replace("-", " ").replace("_", " ").title() if slug else ""

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        return text, page_title