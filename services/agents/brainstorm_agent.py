from typing import AsyncGenerator
from services.ai import get_streaming_ai_response
from services.agents.base import BASE_IDENTITY

BRAINSTORM_SPECIALIST_PROMPT = f"""{BASE_IDENTITY}
You are a sharp thinking partner. You excel at deep ideation, structural planning, and creative expansion.
Your goal is to help turn vague thoughts into clear, actionable structures.

Skills:
- [GENERATE_IDEAS: topic="Context" count=10]
- [PROPOSE_MIND_MAP: title="Name" nodes="JSON_STRING"]
- [PROPOSE_SAVE_REPORT: title="Brief" type="strategy"]

STRATEGY:
1. Deeply analyze the user's concept or problem.
2. Propose structural expansions via [GENERATE_IDEAS].
3. If they approve a direction, use [PROPOSE_MIND_MAP] to visualize the hierarchy.
4. Always maintain a sharp and encouraging tone.
"""

async def run_brainstorm_logic(user_id: str, message: str, context: dict) -> AsyncGenerator[str, None]:
    """Handles brainstorming and ideation requests."""
    system = BRAINSTORM_SPECIALIST_PROMPT
    
    # Enrich with conversation history and focus context
    history = context.get("history", [])
    history_str = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in history[-5:]])
    
    user_prompt = f"""Conversation History:
{history_str}

User Request: {message}

Expand on this concept."""

    async for chunk in get_streaming_ai_response(system, user_prompt):
        yield chunk
