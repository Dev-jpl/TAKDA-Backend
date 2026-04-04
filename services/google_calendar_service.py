from googleapiclient.discovery import build
from .google_auth_service import google_auth_service
from database import supabase
from typing import List, Dict, Any, Optional
import datetime

class GoogleCalendarService:
    def get_calendar_events(self, user_id: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """Fetches events from the user's primary Google Calendar."""
        creds = google_auth_service.get_credentials(user_id)
        if not creds:
            return []

        service = build('calendar', 'v3', credentials=creds)
        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        
        events_result = service.events().list(
            calendarId='primary', 
            timeMin=now,
            maxResults=max_results, 
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        return events

    def sync_events(self, user_id: str) -> List[Dict[str, Any]]:
        """Syncs Google Calendar events to the local Takda events table."""
        g_events = self.get_calendar_events(user_id)
        synced_ids = []

        for g_event in g_events:
            # Map Google event to Takda event structure
            start = g_event['start'].get('dateTime', g_event['start'].get('date'))
            end = g_event['end'].get('dateTime', g_event['end'].get('date'))
            
            event_data = {
                "user_id": user_id,
                "title": g_event.get('summary', 'Untitled Event'),
                "description": g_event.get('description', ''),
                "location": g_event.get('location', ''),
                "start_time": start,
                "end_time": end,
                "metadata": {
                    "source": "google_calendar",
                    "google_event_id": g_event['id'],
                    "htmlLink": g_event.get('htmlLink')
                },
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }

            # Upsert based on google_event_id in metadata
            # Note: We might need a proper column for source_id or just use metadata filtering
            # For simplicity, we'll try to find an existing event with this google_event_id
            existing = supabase.table("events")\
                .select("id")\
                .eq("user_id", user_id)\
                .filter("metadata->>google_event_id", "eq", g_event['id'])\
                .execute()

            if existing.data:
                res = supabase.table("events").update(event_data).eq("id", existing.data[0]['id']).execute()
            else:
                res = supabase.table("events").insert(event_data).execute()
            
            if res.data:
                synced_ids.append(res.data[0]['id'])

        return synced_ids

google_calendar_service = GoogleCalendarService()
