import re
from typing import AsyncGenerator
from services.ai import get_streaming_ai_response
from services.calendar_service import get_events
from config import ASSISTANT_NAME

from services.agents.base import BASE_IDENTITY

CALENDAR_SPECIALIST_PROMPT = f"""{BASE_IDENTITY}
You help the user manage their calendar with clarity and care.
Skills:
- [FETCH_CALENDAR: start="ISO" end="ISO"] (Fetch existing events)
- [PROPOSE_CREATE_EVENT: title="Name" start_time="ISO" end_time="ISO" location="Plain Text"]
- [PROPOSE_UPDATE_EVENT: id="<UUID>" title="New" start_time="ISO"]
- [PROPOSE_DELETE_EVENT: id="<UUID>"]

STRATEGY:
1. If the user asks about their schedule, use [FETCH_CALENDAR].
2. If the info from FETCH is provided, analyze it and report your findings.
3. If they want to add an event, check for conflicts via FETCH first if unsure, then use [PROPOSE_CREATE_EVENT].
4. OMIT attributes if values are unknown.
"""

async def run_calendar_logic(user_id: str, message: str, context: dict) -> AsyncGenerator[str, None]:
    """Specialized loop for Calendar Coordination."""
    
    # 1. Immediate Discovery Check (Agentic Brainstorming)
    # If the user is asking "What's my schedule?", we can proactively fetch.
    if any(k in message.lower() for k in ["schedule", "events", "calendar", "what's my", "list"]):
        # Automatic fetch for the next 7 days unless specified
        start = datetime.now().isoformat()
        end = (datetime.now() + timedelta(days=7)).isoformat()
        events = get_events(user_id, start, end)
        
        if events:
            context_snippet = "\nEXISTING EVENTS:\n" + "\n".join([f"- {e['title']} @ {e['start_at']} [id: {e['id']}]" for e in events])
            message += context_snippet
        else:
            message += "\n(No events found for this period.)"

    # 2. Main Agent Stream
    async for chunk in get_streaming_ai_response(CALENDAR_SPECIALIST_PROMPT, message):
        yield chunk

from datetime import datetime, timedelta