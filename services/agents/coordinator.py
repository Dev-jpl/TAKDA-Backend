from services.ai import get_ai_response_async
import json, re

from config import ASSISTANT_NAME

COORDINATOR_PROMPT = f"""You are {ASSISTANT_NAME}'s intent router inside TAKDA — a personal life OS.

Classify the user's message into one or more of these intents:
TASK       — create, update, delete, or list tasks
CALENDAR   — schedule specific events, set time-blocked reminders, manage calendar entries (use this for "Create an event" or "Schedule an event")
REPORT     — generate reports, summaries, plans, presentations
QUIZ       — create quizzes or flashcards from documents
KNOWLEDGE  — search documents, answer questions from notes
SPACE      — organizing, creating, or renaming hubs/spaces
ARCHITECT  — suggest structural optimizations (merge/split hubs)
CLEANER    — identify or remove stale/inactive hubs
BRIEFING   — daily briefing (combined tasks/events overview)
FOCUS      — help user focus on priorities
BRAINSTORM — creative ideation and planning
CONSTITUTE — identify and merge duplicate tasks
GUARD      — proactive calendar conflict monitoring
CHAT       — regular conversational assistance or knowledge extraction
CLARIFY    — use this if the user wants a TASK/EVENT/SPACE operation but essential parameters are missing.

STRICT CLARIFICATION RULE: If user says "Add a task" but doesn't specify a Hub or details, choose CLARIFY as the primary intent. Do not guess.

Rules:
- A message can have multiple intents (e.g. "add a task and schedule it" = TASK + CALENDAR)
- When in doubt, or if parameters are missing for a tool, use CLARIFY or CHAT
- Always return valid JSON only, no explanation

Return format:
{{"intents": ["TASK"], "primary": "TASK"}}
or
{{"intents": ["ARCHITECT"], "primary": "ARCHITECT"}}
or
{{"intents": ["TASK", "CALENDAR"], "primary": "TASK"}}
"""

class AgentCoordinator:
    @staticmethod
    async def classify_intent(message: str, conversation_history: list = []) -> dict:
        history_context = ""
        if conversation_history:
            last = conversation_history[-3:]
            history_context = "\n".join([f"{m['role']}: {m['content'][:100]}" for m in last])
            history_context = f"\nRecent conversation:\n{history_context}\n"

        user_prompt = f"{history_context}Message to classify: \"{message}\""

        response = await get_ai_response_async(COORDINATOR_PROMPT, user_prompt)
        try:
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except:
            pass
        return {"intents": ["CHAT"], "primary": "CHAT"}