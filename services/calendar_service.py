from datetime import datetime, timedelta
from database import supabase
from typing import List, Optional, Dict, Any
import uuid

def is_valid_uuid(val: Any) -> bool:
    if not val or not isinstance(val, str): return False
    try:
        uuid.UUID(val)
        return True
    except ValueError:
        return False

def get_events(user_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches calendar events for the user with optional date filtering."""
    query = supabase.table("events").select("*").eq("user_id", user_id)
    
    if start_date:
        query = query.gte("start_time", start_date)
    if end_date:
        query = query.lte("end_time", end_date)
        
    res = query.order("start_time", desc=False).execute()
    return res.data or []

def create_event(user_id: str, title: str, start_time: str, end_time: Optional[str] = None, location: Optional[str] = None) -> Dict[str, Any]:
    """Creates a new calendar event."""
    if not start_time:
        raise ValueError("Missing start_time.")
    
    st = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    
    if end_time:
        et = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
    else:
        # Default duration: 1 hour
        et = st + timedelta(hours=1)
        
    res = supabase.table("events").insert({
        "user_id": user_id,
        "title": title,
        "start_time": st.isoformat(),
        "end_time": et.isoformat(),
        "location": location
    }).execute()
    
    return res.data[0] if res.data else {}

def update_event(event_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Updates an existing calendar event."""
    # Ensure nested objects or special fields are handled if necessary
    res = supabase.table("events").update(updates).eq("id", event_id).execute()
    return res.data[0] if res.data else {}

def delete_event(event_id: str) -> bool:
    """Deletes a calendar event."""
    res = supabase.table("events").delete().eq("id", event_id).execute()
    return True
