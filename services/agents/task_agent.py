from services.ai import get_streaming_ai_response, get_ai_response
import json
import re

TASK_PROMPT = """You are the Kalay Task Agent. Your job is to extract actionable items from a conversation and map them to the Track module.

TASK FIELDS:
- title: Concise and action-oriented.
- priority: urgent, high, low.
- status: todo, in_progress, done.
- hub_id: Select the most appropriate hub if multiple.

Output: Provide a conversational confirmation followed by the task marker.
Example: I've created a task for you: [CREATE_TASK: title="Build the API", priority="high", hub_id="..."]
"""

async def extract_tasks_stream(user_id: str, message: str, context_hubs: str):
    system_prompt = TASK_PROMPT
    user_prompt = f"Message: {message}\nContext Hubs:\n{context_hubs}\n\nPlease identify tasks."

    async for chunk in get_streaming_ai_response(system_prompt, user_prompt):
        yield chunk
