from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import supabase

router = APIRouter(prefix="/spaces", tags=["spaces"])


class SpaceCreate(BaseModel):
    user_id: str
    name: str
    icon: str = "Folder"
    color: str = "#7F77DD"
    category: str = "personal"
    description: Optional[str] = None


class SpaceUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    order_index: Optional[int] = None


# --- Get all spaces (top level categories) ---
@router.get("/{user_id}")
async def get_spaces(user_id: str):
    # Get spaces with a count of hubs inside them
    # Note: we filter by category if needed later
    spaces = supabase.table("spaces") \
        .select("*, hubs(count)") \
        .eq("user_id", user_id) \
        .order("order_index") \
        .execute()
    return spaces.data


# --- Create space (Category) ---
@router.post("/")
async def create_space(body: SpaceCreate):
    # Get current max order
    existing = supabase.table("spaces") \
        .select("order_index") \
        .eq("user_id", body.user_id) \
        .order("order_index", desc=True) \
        .limit(1) \
        .execute()

    next_order = 0
    if existing.data:
        next_order = existing.data[0]["order_index"] + 1

    space = supabase.table("spaces").insert({
        "user_id": body.user_id,
        "name": body.name,
        "icon": body.icon,
        "color": body.color,
        "category": body.category,
        "description": body.description,
        "order_index": next_order,
    }).execute()

    if not space.data:
        raise HTTPException(status_code=500, detail="Failed to create space")

    # No longer inserting space_modules here as they belong to hubs now
    return space.data[0]


# --- Update space ---
@router.patch("/{space_id}")
async def update_space(space_id: str, body: SpaceUpdate):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    space = supabase.table("spaces") \
        .update(updates) \
        .eq("id", space_id) \
        .execute()

    return space.data[0]


# --- Delete space ---
@router.delete("/{space_id}")
async def delete_space(space_id: str):
    supabase.table("spaces") \
        .delete() \
        .eq("id", space_id) \
        .execute()
    return {"deleted": True}


# --- Reorder spaces ---
class ReorderBody(BaseModel):
    space_ids: list[str]

@router.post("/reorder")
async def reorder_spaces(body: ReorderBody):
    for index, space_id in enumerate(body.space_ids):
        supabase.table("spaces") \
            .update({"order_index": index}) \
            .eq("id", space_id) \
            .execute()
    return {"reordered": True}