from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from database import supabase

router = APIRouter(prefix="/hubs", tags=["hubs"])

class HubCreate(BaseModel):
    space_id: str
    user_id: str
    name: str
    icon: str = "Circle"
    color: str = "#7F77DD"
    description: Optional[str] = None

class HubUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None
    order_index: Optional[int] = None

class ReorderHubsBody(BaseModel):
    hub_ids: List[str]

# --- Get hubs in a space ---
@router.get("/{space_id}")
async def get_hubs(space_id: str):
    hubs = supabase.table("hubs") \
        .select("*, hub_modules(*)") \
        .eq("space_id", space_id) \
        .order("order_index") \
        .execute()
    return hubs.data

# --- Create hub ---
@router.post("/")
async def create_hub(body: HubCreate):
    # Get current max order
    existing = supabase.table("hubs") \
        .select("order_index") \
        .eq("space_id", body.space_id) \
        .order("order_index", desc=True) \
        .limit(1) \
        .execute()

    next_order = 0
    if existing.data:
        next_order = existing.data[0]["order_index"] + 1

    hub = supabase.table("hubs").insert({
        "space_id": body.space_id,
        "user_id": body.user_id,
        "name": body.name,
        "icon": body.icon,
        "color": body.color,
        "description": body.description,
        "order_index": next_order,
    }).execute()

    if not hub.data:
        raise HTTPException(status_code=500, detail="Failed to create hub")

    hub_id = hub.data[0]["id"]

    # Enable all modules by default for the hub
    modules = ["track", "annotate", "knowledge", "deliver", "automate"]
    for i, module in enumerate(modules):
        try:
            supabase.table("hub_modules").insert({
                "hub_id": hub_id,
                "module": module,
                "order_index": i,
                "is_enabled": True,
            }).execute()
        except Exception as e:
            print(f"Warning: could not insert hub_module '{module}': {e}")

    return hub.data[0]

# --- Update hub ---
@router.patch("/{hub_id}")
async def update_hub(hub_id: str, body: HubUpdate):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    hub = supabase.table("hubs") \
        .update(updates) \
        .eq("id", hub_id) \
        .execute()

    if not hub.data:
        raise HTTPException(status_code=404, detail="Hub not found")

    return hub.data[0]

# --- Delete hub ---
@router.delete("/{hub_id}")
async def delete_hub(hub_id: str):
    supabase.table("hubs") \
        .delete() \
        .eq("id", hub_id) \
        .execute()
    return {"status": "deleted"}

# --- Reorder hubs ---
@router.post("/reorder")
async def reorder_hubs(body: ReorderHubsBody):
    for index, hub_id in enumerate(body.hub_ids):
        supabase.table("hubs") \
            .update({"order_index": index}) \
            .eq("id", hub_id) \
            .execute()
    return {"status": "reordered"}
