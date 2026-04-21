from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
from database import supabase

router = APIRouter(prefix="/screens", tags=["screens"])


class ScreenCreate(BaseModel):
    user_id: str
    name: str
    space_id: Optional[str] = None  # nullable — cross-space screens have no parent space
    position: int = 0


class ScreenUpdate(BaseModel):
    name: Optional[str] = None
    position: Optional[int] = None


class WidgetCreate(BaseModel):
    screen_id: str
    hub_id: Optional[str] = None
    type: str  # 'tasks' | 'notes' | 'docs' | 'outcomes' | 'hub_overview'
    title: Optional[str] = None
    position: int = 0
    config: Optional[dict[str, Any]] = None


class WidgetUpdate(BaseModel):
    hub_id: Optional[str] = None
    title: Optional[str] = None
    position: Optional[int] = None
    config: Optional[dict[str, Any]] = None


# ── Screens ───────────────────────────────────────────────────────────────────

@router.get("/by-user/{user_id}")
async def get_screens_by_user(user_id: str):
    """All screens belonging to a user (cross-space management view)."""
    result = supabase.table("screens") \
        .select("*") \
        .eq("user_id", user_id) \
        .order("position", desc=False) \
        .order("created_at", desc=True) \
        .execute()
    return result.data


@router.get("/by-space/{space_id}")
async def get_screens_by_space(space_id: str):
    """Screens scoped to a specific space."""
    result = supabase.table("screens") \
        .select("*") \
        .eq("space_id", space_id) \
        .order("position", desc=False) \
        .order("created_at", desc=True) \
        .execute()
    return result.data


@router.post("/")
async def create_screen(body: ScreenCreate):
    payload: dict[str, Any] = {
        "user_id": body.user_id,
        "name": body.name,
        "position": body.position,
    }
    if body.space_id:
        payload["space_id"] = body.space_id

    result = supabase.table("screens").insert(payload).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create screen")
    return result.data[0]


@router.patch("/{screen_id}")
async def update_screen(screen_id: str, body: ScreenUpdate):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    result = supabase.table("screens").update(updates).eq("id", screen_id).execute()
    return result.data[0]


@router.delete("/{screen_id}")
async def delete_screen(screen_id: str):
    supabase.table("screens").delete().eq("id", screen_id).execute()
    return {"deleted": True}


# ── Widgets ───────────────────────────────────────────────────────────────────

@router.get("/{screen_id}/widgets")
async def get_widgets(screen_id: str):
    result = supabase.table("screen_widgets") \
        .select("*") \
        .eq("screen_id", screen_id) \
        .order("position") \
        .execute()
    return result.data


@router.post("/widgets")
async def create_widget(body: WidgetCreate):
    result = supabase.table("screen_widgets").insert({
        "screen_id": body.screen_id,
        "hub_id": body.hub_id,
        "type": body.type,
        "title": body.title,
        "position": body.position,
        "config": body.config or {},
    }).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create widget")
    return result.data[0]


@router.patch("/widgets/{widget_id}")
async def update_widget(widget_id: str, body: WidgetUpdate):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    result = supabase.table("screen_widgets").update(updates).eq("id", widget_id).execute()
    return result.data[0]


@router.delete("/widgets/{widget_id}")
async def delete_widget(widget_id: str):
    supabase.table("screen_widgets").delete().eq("id", widget_id).execute()
    return {"deleted": True}
