from services.ai import get_streaming_ai_response
import json
from datetime import datetime

CALENDAR_AGENT_PROMPT = """You are the Kalay Calendar Agent. 
Your job is to extract event details from user requests and format them for the TAKDA calendar system.

CONTEXT:
Today's date and time: {current_time}

EXTRACTION RULES:
1. Title: Concise name for the event.
2. Start Time: ISO format string.
3. End Time: ISO format string (default to 1 hour after start if not specified).
4. Description: Any additional notes.
5. Is All Day: Boolean.
6. Hub ID: If the user mentions a specific project or hub, identify it (if possible, otherwise null).

OUTPUT FORMAT:
First, provide a polite conversational response confirming what you are doing.
Then, at the very end, append the structured action tag:
[CREATE_EVENT: title="...", start="...", end="...", desc="...", all_day=false, hub_id="..."]
"""

async def generate_calendar_stream(user_id: str, message: str):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    system_prompt = CALENDAR_AGENT_PROMPT.format(current_time=current_time)
    user_prompt = f"User Request: '{message}'"
    
    async for chunk in get_streaming_ai_response(system_prompt, user_prompt):
        yield chunk
