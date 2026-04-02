from services.ai import get_streaming_ai_response
from datetime import datetime

CALENDAR_PROMPT = """You are Kalay's calendar agent inside TAKDA.

Extract event details and confirm them naturally.

Rules:
- Be brief. One sentence confirmation before the tag.
- Infer duration: meetings = 1hr, workouts = 1hr, quick tasks = 30min
- Use ISO 8601 for dates
- If day is mentioned but not time, default to 9:00 AM

Output EXACTLY this tag on its own line:
[CREATE_EVENT: title="..." start="2026-04-02T09:00:00" end="2026-04-02T10:00:00" all_day=false]
"""

async def run_calendar_agent_stream(message: str, conversation_history: list = []):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")

    history_text = "\n".join([
        f"{m['role']}: {m['content'][:150]}"
        for m in (conversation_history[-4:] if conversation_history else [])
    ])

    user_prompt = f"""Today: {current_time}

Recent conversation:
{history_text}

User request: "{message}"

Schedule this event."""

    async for chunk in get_streaming_ai_response(CALENDAR_PROMPT, user_prompt):
        yield chunk