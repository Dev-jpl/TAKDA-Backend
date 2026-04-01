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


class ChatRequest(BaseModel):
    query: str
    user_id: str
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
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    content = await file.read()

    try:
        text = extract_pdf_text(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF extraction failed: {str(e)}")

    doc = supabase.table("documents").insert({
        "user_id": user_id,
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
        text = await extract_url_text(body.url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"URL extraction failed: {str(e)}")

    title = body.title or body.url.split("/")[-1] or "Untitled"

    doc = supabase.table("documents").insert({
        "user_id": body.user_id,
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
async def get_documents(user_id: str):
    docs = supabase.table("documents") \
        .select("id, title, source_type, source_url, created_at") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .execute()

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


async def extract_url_text(url: str) -> str:
    import httpx
    from bs4 import BeautifulSoup

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, follow_redirects=True)
        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        return soup.get_text(separator="\n", strip=True)