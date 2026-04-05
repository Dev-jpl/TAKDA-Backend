from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from database import supabase
from services.google_calendar_service import google_calendar_service
import uuid

router = APIRouter(prefix="/events", tags=["events"])

class EventBase(BaseModel):
    title: str
    description: Optional[str] = None
    people: Optional[str] = None
    location: Optional[str] = None
    start_at: datetime
    end_at: datetime
    is_all_day: bool = False
    calendar_id: Optional[str] = None
    hub_id: Optional[str] = None
    color: Optional[str] = None
    metadata: Optional[dict] = {}

class EventCreate(EventBase):
    user_id: str

class EventUpdate(BaseModel):
    people: Optional[str] = None
    location: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    is_all_day: Optional[bool] = None
    calendar_id: Optional[str] = None
    hub_id: Optional[str] = None
    color: Optional[str] = None
    metadata: Optional[dict] = None

@router.get("/")
async def get_events(user_id: str, hub_id: Optional[str] = None, calendar_id: Optional[str] = None):
    query = supabase.table("events").select("*").eq("user_id", user_id)
    if hub_id:
        query = query.eq("hub_id", hub_id)
    if calendar_id:
        query = query.eq("calendar_id", calendar_id)
    
    res = query.order("start_at", desc=False).execute()
    return res.data

def to_dict(model: BaseModel, exclude_unset: bool = False):
    """Helper to convert Pydantic model to dict with ISO strings for datetimes."""
    d = model.dict(exclude_unset=exclude_unset)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat().replace('+00:00', 'Z')
    return d

@router.post("/")
async def create_event(event: EventCreate):
    # Check if user has Google integration
    google_event_id = None
    event_dict = to_dict(event)
    
    if google_calendar_service.is_connected(event.user_id):
        try:
            google_event_id = google_calendar_service.create_calendar_event(
                event.user_id, 
                event_dict
            )
            if google_event_id:
                # Update event_dict with google metadata
                if not event_dict.get("metadata"):
                    event_dict["metadata"] = {}
                event_dict["metadata"]["google_event_id"] = google_event_id
                event_dict["metadata"]["source"] = "takda_synced"
        except Exception as e:
            print(f"Failed to push to Google Calendar: {e}")

    res = supabase.table("events").insert(event_dict).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create event")
    return res.data[0]

@router.patch("/{event_id}")
async def update_event(event_id: str, event: EventUpdate):
    # Get existing event to check for google_event_id
    existing = supabase.table("events").select("*").eq("id", event_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Event not found")
    
    current_event = existing.data[0]
    user_id = current_event["user_id"]
    google_event_id = (current_event.get("metadata") or {}).get("google_event_id")
    
    update_dict = to_dict(event, exclude_unset=True)

    # Update on Google if exists
    if google_event_id and google_calendar_service.is_connected(user_id):
        try:
            google_calendar_service.update_calendar_event(
                user_id, 
                google_event_id, 
                update_dict
            )
        except Exception as e:
            print(f"Failed to update Google Calendar: {e}")

    res = supabase.table("events").update(update_dict).eq("id", event_id).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to update event")
    return res.data[0]

@router.delete("/{event_id}")
async def delete_event(event_id: str):
    # Get existing event to check for google_event_id
    existing = supabase.table("events").select("*").eq("id", event_id).execute()
    if existing.data:
        current_event = existing.data[0]
        user_id = current_event["user_id"]
        google_event_id = (current_event.get("metadata") or {}).get("google_event_id")

        # Delete on Google if exists
        if google_event_id and google_calendar_service.is_connected(user_id):
            try:
                google_calendar_service.delete_calendar_event(user_id, google_event_id)
            except Exception as e:
                print(f"Failed to delete from Google Calendar: {e}")

    res = supabase.table("events").delete().eq("id", event_id).execute()
    return {"status": "deleted"}
