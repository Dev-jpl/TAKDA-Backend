from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
from database import supabase

router = APIRouter(prefix="/space-tools", tags=["space-tools"])

class SpaceToolCreate(BaseModel):
    space_id: str
    name: str
    type: str # 'webhook', 'api_key', 'oauth', 'custom'
    config: Optional[dict] = {}

class SpaceToolUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    config: Optional[dict] = None
    is_active: Optional[bool] = None

@router.get("/{space_id}")
async def get_space_tools(space_id: str):
    # Depending on RLS, we may need to fetch with user context, but router is open right now
    tools = supabase.table("space_tools") \
        .select("*") \
        .eq("space_id", space_id) \
        .order("created_at", desc=True) \
        .execute()
    return tools.data

@router.post("/")
async def create_space_tool(body: SpaceToolCreate):
    tool = supabase.table("space_tools").insert({
        "space_id": body.space_id,
        "name": body.name,
        "type": body.type,
        "config": body.config,
    }).execute()

    if not tool.data:
        raise HTTPException(status_code=500, detail="Failed to create space tool")

    return tool.data[0]

@router.patch("/{tool_id}")
async def update_space_tool(tool_id: str, body: SpaceToolUpdate):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    tool = supabase.table("space_tools") \
        .update(updates) \
        .eq("id", tool_id) \
        .execute()

    if not tool.data:
        raise HTTPException(status_code=404, detail="Tool not found")

    return tool.data[0]

@router.delete("/{tool_id}")
async def delete_space_tool(tool_id: str):
    supabase.table("space_tools") \
        .delete() \
        .eq("id", tool_id) \
        .execute()
    return {"deleted": True}
