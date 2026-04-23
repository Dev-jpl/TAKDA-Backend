from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
from database import supabase

router = APIRouter(prefix="/modules", tags=["modules"])

class ModuleEntryCreate(BaseModel):
    user_id: str
    hub_id: Optional[str] = None
    data: dict[str, Any]

class ModuleDefinitionCreate(BaseModel):
    user_id: str
    slug: str
    name: str
    description: Optional[str] = None
    schema_fields: list[dict[str, Any]]
    layout: dict[str, Any]
    is_global: bool = False

@router.get("/definitions")
async def get_module_definitions():
    """Get all global module definitions, or user's custom ones."""
    res = supabase.table("module_definitions").select("*").execute()
    return res.data

@router.post("/definitions")
async def create_module_definition(body: ModuleDefinitionCreate):
    """Create a new module definition."""
    res = supabase.table("module_definitions").insert({
        "user_id": body.user_id,
        "slug": body.slug,
        "name": body.name,
        "description": body.description,
        "schema": body.schema_fields,
        "layout": body.layout,
        "is_global": body.is_global
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create module definition")
    return res.data[0]

@router.put("/definitions/{def_id}")
async def update_module_definition(def_id: str, body: ModuleDefinitionCreate):
    """Update an existing module definition."""
    res = supabase.table("module_definitions").update({
        "slug": body.slug,
        "name": body.name,
        "description": body.description,
        "schema": body.schema_fields,
        "layout": body.layout,
        "is_global": body.is_global
    }).eq("id", def_id).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to update module definition")
    return res.data[0]

@router.get("/{def_id}/entries")
async def get_module_entries(def_id: str, hub_id: Optional[str] = None):
    """Get all entries for a specific module definition, optionally filtered by hub."""
    query = supabase.table("module_entries").select("*").eq("module_def_id", def_id)
    if hub_id:
        query = query.or_(f"hub_id.eq.{hub_id},hub_id.is.null")
    res = query.order("created_at", desc=True).execute()
    return res.data

@router.post("/{def_id}/entries")
async def create_module_entry(def_id: str, body: ModuleEntryCreate):
    """Create a new entry for a module."""
    row = {
        "module_def_id": def_id,
        "user_id": body.user_id,
        "data": body.data,
    }
    if body.hub_id:
        row["hub_id"] = body.hub_id

    res = supabase.table("module_entries").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create module entry")
    return res.data[0]

@router.delete("/entries/{entry_id}")
async def delete_module_entry(entry_id: str):
    """Delete a module entry."""
    res = supabase.table("module_entries").delete().eq("id", entry_id).execute()
    return {"status": "success"}
