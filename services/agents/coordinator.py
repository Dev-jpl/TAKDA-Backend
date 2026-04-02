from services.ai import get_ai_response_async
import json, re

COORDINATOR_PROMPT = """You are Kalay's intent router inside TAKDA — a personal life OS.

Classify the user's message into one or more of these intents:
TASK       — create, update, delete, or list tasks
CALENDAR   — schedule events, set reminders
REPORT     — generate reports, summaries, plans, presentations
QUIZ       — create quizzes or flashcards from documents
KNOWLEDGE  — search documents, answer questions from notes
CRUD_SPACE — create or manage spaces and hubs
CHAT       — general conversation, greetings, unclear

Rules:
- A message can have multiple intents (e.g. "add a task and schedule it" = TASK + CALENDAR)
- When in doubt, use CHAT
- Always return valid JSON only, no explanation

Return format:
{"intents": ["TASK"], "primary": "TASK"}
or
{"intents": ["TASK", "CALENDAR"], "primary": "TASK"}
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