from googleapiclient.discovery import build
from .google_auth_service import google_auth_service
from database import supabase
from typing import List, Dict, Any, Optional
import datetime

class GoogleCalendarService:
    def is_connected(self, user_id: str) -> bool:
        """Checks if the user has an active Google integration."""
        creds = google_auth_service.get_credentials(user_id)
        return creds is not None

    def create_calendar_event(self, user_id: str, event_data: Dict[str, Any]) -> Optional[str]:
        """Creates an event in the user's primary Google Calendar."""
        creds = google_auth_service.get_credentials(user_id)
        if not creds:
            return None

        service = build('calendar', 'v3', credentials=creds)
        
        # Prepare Google event structure
        g_event = {
            'summary': event_data.get('title'),
            'location': event_data.get('location', ''),
            'description': event_data.get('description', ''),
            'start': {
                'dateTime': event_data.get('start_at'),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': event_data.get('end_at'),
                'timeZone': 'UTC',
            },
        }

        created_event = service.events().insert(calendarId='primary', body=g_event).execute()
        return created_event.get('id')

    def update_calendar_event(self, user_id: str, google_event_id: str, event_data: Dict[str, Any]) -> bool:
        """Updates an existing event in the user's Google Calendar."""
        creds = google_auth_service.get_credentials(user_id)
        if not creds:
            return False

        service = build('calendar', 'v3', credentials=creds)
        
        # Get existing event first to maintain consistency
        try:
            g_event = service.events().get(calendarId='primary', eventId=google_event_id).execute()
            
            g_event['summary'] = event_data.get('title', g_event['summary'])
            g_event['description'] = event_data.get('description', g_event['description'])
            g_event['location'] = event_data.get('location', g_event['location'])
            
            if 'start_at' in event_data:
                g_event['start']['dateTime'] = event_data['start_at']
            if 'end_at' in event_data:
                g_event['end']['dateTime'] = event_data['end_at']

            service.events().update(calendarId='primary', eventId=google_event_id, body=g_event).execute()
            return True
        except Exception as e:
            print(f"Error updating Google event: {e}")
            return False

    def delete_calendar_event(self, user_id: str, google_event_id: str) -> bool:
        """Deletes an event from the user's Google Calendar."""
        creds = google_auth_service.get_credentials(user_id)
        if not creds:
            return False

        service = build('calendar', 'v3', credentials=creds)
        try:
            service.events().delete(calendarId='primary', eventId=google_event_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting Google event: {e}")
            return False

    def get_calendar_events(self, user_id: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """Fetches events from the user's primary Google Calendar."""
        creds = google_auth_service.get_credentials(user_id)
        if not creds:
            return []

        service = build('calendar', 'v3', credentials=creds)
        now = datetime.datetime.now(datetime.timezone.utc)
        lookback = (now - datetime.timedelta(hours=12)).isoformat().replace('+00:00', 'Z')
        
        try:
            events_result = service.events().list(
                calendarId='primary', 
                timeMin=lookback,
                maxResults=max_results, 
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            return events_result.get('items', [])
        except Exception as e:
            print(f"Error fetching Google events: {e}")
            return []

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
                "start_at": start,
                "end_at": end,
                "metadata": {
                    "source": "google_calendar",
                    "google_event_id": g_event['id'],
                    "htmlLink": g_event.get('htmlLink')
                },
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }

            # Upsert based on google_event_id in metadata
            try:
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
            except Exception as e:
                print(f"Error syncing individual event {g_event.get('summary')}: {e}")

        return synced_ids

google_calendar_service = GoogleCalendarService()
