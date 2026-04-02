from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from database import supabase

router = APIRouter(prefix="/deliver", tags=["deliver"])

class DeliveryCreate(BaseModel):
    hub_id: str
    user_id: str
    content: str
    type: str  # update | decision | delivered | question
    metadata: Optional[dict] = None

class DeliveryUpdate(BaseModel):
    content: Optional[str] = None
    type: Optional[str] = None
    metadata: Optional[dict] = None

@router.get("/{hub_id}")
async def get_deliveries(hub_id: str):
    """Fetch all project dispatches for a given hub."""
    res = supabase.table("deliveries") \
        .select("*") \
        .eq("hub_id", hub_id) \
        .order("created_at", desc=True) \
        .execute()
    return res.data

@router.post("/")
async def create_delivery(body: DeliveryCreate):
    """Create a new project dispatch."""
    res = supabase.table("deliveries").insert({
        "hub_id": body.hub_id,
        "user_id": body.user_id,
        "content": body.content,
        "type": body.type,
        "metadata": body.metadata,
    }).execute()
    
    if not res.data:
        raise HTTPException(status_code=400, detail="Could not create dispatch")
        
    return res.data[0]

@router.delete("/{delivery_id}")
async def delete_delivery(delivery_id: str):
    """Remove a project dispatch."""
    supabase.table("deliveries") \
        .delete() \
        .eq("id", delivery_id) \
        .execute()
    return {"deleted": True}
