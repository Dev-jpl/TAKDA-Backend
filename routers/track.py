from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import supabase

router = APIRouter(prefix="/track", tags=["track"])


class TaskCreate(BaseModel):
    hub_id: str
    user_id: str
    title: str
    priority: Optional[str] = "low"  # urgent | high | low
    status: Optional[str] = "todo"   # todo | in_progress | done
    due_date: Optional[str] = None
    time_estimate: Optional[int] = None  # minutes
    notes: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[str] = None
    time_estimate: Optional[int] = None
    notes: Optional[str] = None


# --- Get tasks ---
@router.get("/{hub_id}")
async def get_tasks(hub_id: str):
    tasks = supabase.table("tasks") \
        .select("*") \
        .eq("hub_id", hub_id) \
        .order("created_at", desc=False) \
        .execute()
    return tasks.data


# --- Create task ---
@router.post("/")
async def create_task(body: TaskCreate):
    task = supabase.table("tasks").insert({
        "hub_id": body.hub_id,
        "user_id": body.user_id,
        "title": body.title,
        "priority": body.priority,
        "status": body.status,
        "due_date": body.due_date,
        "time_estimate": body.time_estimate,
        "notes": body.notes,
    }).execute()
    return task.data[0]


# --- Update task ---
@router.patch("/{task_id}")
async def update_task(task_id: str, body: TaskUpdate):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    task = supabase.table("tasks") \
        .update(updates) \
        .eq("id", task_id) \
        .execute()
    return task.data[0]


# --- Delete task ---
@router.delete("/{task_id}")
async def delete_task(task_id: str):
    supabase.table("tasks") \
        .delete() \
        .eq("id", task_id) \
        .execute()
    return {"deleted": True}