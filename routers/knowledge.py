from fastapi import APIRouter, UploadFile, File, HTTPException, Header
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
    space_id: Optional[str] = None


class ChatRequest(BaseModel):
    query: str
    user_id: str
    space_id: Optional[str] = None
    document_ids: Optional[list[str]] = None


class DocumentCreate(BaseModel):
    title: str
    source_type: str
    raw_content: str
    source_url: Optional[str] = None
    user_id: str


# --- Upload PDF ---
@router.post("/upload/pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    user_id: str = Header(...),
    space_id: Optional[str] = Header(None),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    # Normalize empty-string header to None
    if not space_id:
        space_id = None

    content = await file.read()

    try:
        text = extract_pdf_text(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF extraction failed: {str(e)}")

    doc = supabase.table("documents").insert({
        "user_id": user_id,
        "space_id": space_id,
        "title": file.filename.replace(".pdf", ""),
        "source_type": "pdf",
        "raw_content": text,
    }).execute()

    document_id = doc.data[0]["id"]

    await process_document(document_id, text)

    return {
        "document_id": document_id,
        "title": file.filename,
        "chunks_processed": True,
    }


# --- Upload URL ---
@router.post("/upload/url")
async def upload_url(body: URLRequest):
    try:
        text, page_title = await extract_url_text(body.url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"URL extraction failed: {str(e)}")

    title = body.title or page_title or "Untitled"

    doc = supabase.table("documents").insert({
        "user_id": body.user_id,
        "space_id": body.space_id,
        "title": title,
        "source_type": "url",
        "source_url": body.url,
        "raw_content": text,
    }).execute()

    document_id = doc.data[0]["id"]

    await process_document(document_id, text)

    return {
        "document_id": document_id,
        "title": title,
        "chunks_processed": True,
    }


# --- Upload plain text / markdown ---
@router.post("/upload/text")
async def upload_text(body: DocumentCreate):
    doc = supabase.table("documents").insert({
        "user_id": body.user_id,
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


# --- Get all documents ---
@router.get("/documents/{user_id}")
async def get_documents(user_id: str, space_id: Optional[str] = None):
    query = supabase.table("documents") \
        .select("id, title, source_type, source_url, created_at") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True)

    if space_id:
        query = query.eq("space_id", space_id)

    docs = query.execute()
    return docs.data


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
    response = await chat_with_documents(
        query=body.query,
        user_id=body.user_id,
        space_id=body.space_id,
        document_ids=body.document_ids,
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

        # Extract title: <title> tag → first <h1> → URL slug fallback
        page_title = ""
        if soup.title and soup.title.string:
            page_title = soup.title.string.strip()
        elif soup.find("h1"):
            page_title = soup.find("h1").get_text(strip=True)
        else:
            # Derive from URL: strip trailing slash, take last segment, humanize
            slug = url.rstrip("/").split("/")[-1]
            page_title = slug.replace("-", " ").replace("_", " ").title() if slug else ""

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        return text, page_title