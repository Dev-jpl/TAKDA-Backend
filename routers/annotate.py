from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from database import supabase

router = APIRouter(prefix="/annotate", tags=["annotate"])

class AnnotationCreate(BaseModel):
    hub_id: str
    user_id: str
    document_id: Optional[str] = None
    content: str
    category: str  # idea | reference | action

class AnnotationUpdate(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None

@router.get("/{hub_id}")
async def get_annotations(hub_id: str):
    """Fetch all annotations for a given hub."""
    res = supabase.table("annotations") \
        .select("*") \
        .eq("hub_id", hub_id) \
        .order("created_at", desc=True) \
        .execute()
    return res.data

@router.get("/document/{document_id}")
async def get_document_annotations(document_id: str):
    """Fetch all annotations for a specific document."""
    res = supabase.table("annotations") \
        .select("*") \
        .eq("document_id", document_id) \
        .order("created_at", desc=True) \
        .execute()
    return res.data

@router.post("/")
async def create_annotation(body: AnnotationCreate):
    """Create a new insight/annotation."""
    res = supabase.table("annotations").insert({
        "hub_id": body.hub_id,
        "user_id": body.user_id,
        "document_id": body.document_id,
        "content": body.content,
        "category": body.category,
    }).execute()
    
    if not res.data:
        raise HTTPException(status_code=400, detail="Could not create annotation")
        
    return res.data[0]

@router.patch("/{annotation_id}")
async def update_annotation(annotation_id: str, body: AnnotationUpdate):
    """Update an existing annotation."""
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
        
    res = supabase.table("annotations") \
        .update(updates) \
        .eq("id", annotation_id) \
        .execute()
        
    if not res.data:
        raise HTTPException(status_code=404, detail="Annotation not found")
        
    return res.data[0]

@router.delete("/{annotation_id}")
async def delete_annotation(annotation_id: str):
    """Delete an annotation."""
    supabase.table("annotations") \
        .delete() \
        .eq("id", annotation_id) \
        .execute()
    return {"deleted": True}
