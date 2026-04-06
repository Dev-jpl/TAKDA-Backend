from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import supabase

router = APIRouter(prefix="/vault", tags=["vault"])


class VaultItemCreate(BaseModel):
    user_id: str
    content: str
    content_type: str = "text"


class AcceptBody(BaseModel):
    hub_id: str
    module: str = "track"


@router.get("/{user_id}")
async def get_vault_items(user_id: str, status: Optional[str] = None):
    q = supabase.table("vault_items") \
        .select("*") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True)
    if status:
        q = q.eq("status", status)
    res = q.execute()
    return res.data or []


@router.post("/")
async def create_vault_item(body: VaultItemCreate):
    res = supabase.table("vault_items").insert({
        "user_id": body.user_id,
        "content": body.content,
        "content_type": body.content_type,
        "status": "unprocessed",
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create vault item")
    return res.data[0]


@router.patch("/{item_id}/accept")
async def accept_suggestion(item_id: str, body: AcceptBody):
    res = supabase.table("vault_items").update({
        "status": "processed",
        "updated_at": "now()",
    }).eq("id", item_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Item not found")

    # Route to the appropriate module table
    item = res.data[0]
    if body.module == "track":
        supabase.table("tasks").insert({
            "user_id": item["user_id"],
            "hub_id": body.hub_id,
            "title": item["content"][:200],
            "status": "todo",
            "priority": "low",
        }).execute()

    return {"status": "accepted", "id": item_id}


@router.patch("/{item_id}/dismiss")
async def dismiss_suggestion(item_id: str):
    res = supabase.table("vault_items").update({
        "status": "dismissed",
        "updated_at": "now()",
    }).eq("id", item_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"status": "dismissed", "id": item_id}


@router.delete("/{item_id}")
async def delete_vault_item(item_id: str):
    supabase.table("vault_items").delete().eq("id", item_id).execute()
    return {"status": "deleted", "id": item_id}
