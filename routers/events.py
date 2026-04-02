from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from database import supabase
import uuid

router = APIRouter(prefix="/events", tags=["events"])

class EventBase(BaseModel):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    is_all_day: bool = False
    hub_id: Optional[str] = None
    color: Optional[str] = None
    metadata: Optional[dict] = {}

class EventCreate(EventBase):
    user_id: str

class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_all_day: Optional[bool] = None
    hub_id: Optional[str] = None
    color: Optional[str] = None
    metadata: Optional[dict] = None

@router.get("/")
async def get_events(user_id: str, hub_id: Optional[str] = None):
    query = supabase.table("events").select("*").eq("user_id", user_id)
    if hub_id:
        query = query.eq("hub_id", hub_id)
    
    res = query.order("start_time", desc=False).execute()
    return res.data

@router.post("/")
async def create_event(event: EventCreate):
    res = supabase.table("events").insert(event.dict()).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create event")
    return res.data[0]

@router.patch("/{event_id}")
async def update_event(event_id: str, event: EventUpdate):
    res = supabase.table("events").update(event.dict(exclude_unset=True)).eq("id", event_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Event not found")
    return res.data[0]

@router.delete("/{event_id}")
async def delete_event(event_id: str):
    res = supabase.table("events").delete().eq("id", event_id).execute()
    return {"status": "deleted"}
