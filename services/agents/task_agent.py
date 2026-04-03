from services.ai import get_streaming_ai_response
from database import supabase
from config import ASSISTANT_NAME

TASK_PROMPT = f"""You are {ASSISTANT_NAME}'s task agent inside TAKDA.

Your job: extract tasks from the user's message and create them.

Rules:
- Be brief and warm. Max 2 sentences before the action tag.
- Always use the most relevant hub_id from context.
- Priority inference: "urgent/asap/today" = urgent, "important" = high, default = low
- Status default: todo

After creating, output EXACTLY this tag on its own line:
[CREATE_TASK: title="..." priority="low|high|urgent" status="todo" hub_id="..."]

If updating:
[UPDATE_TASK: id="..." status="in_progress|done|todo" priority="..." title="..."]

If the hub is unclear, pick the first hub from context.
"""

async def run_task_agent_stream(message: str, context_hubs: list, conversation_history: list = []):
    hubs_text = "\n".join([
        f"- {h.get('name','?')} (id: {h.get('id','?')}, space: {h.get('space_name','?')})"
        for h in context_hubs
    ]) or "No hubs available."

    history_text = "\n".join([
        f"{m['role']}: {m['content'][:150]}"
        for m in (conversation_history[-4:] if conversation_history else [])
    ])

    user_prompt = f"""Available hubs:
{hubs_text}

Recent conversation:
{history_text}

User message: "{message}"

Extract and create the task(s)."""

    async for chunk in get_streaming_ai_response(TASK_PROMPT, user_prompt):
        yield chunk


async def execute_task_action(tag_content: str, user_id: str) -> dict:
    import re
    params = {}
    for match in re.finditer(r'(\w+)="([^"]*)"', tag_content):
        params[match.group(1)] = match.group(2)

    if not params.get("title") or not params.get("hub_id"):
        return {"error": "missing required fields"}

    result = supabase.table("tasks").insert({
        "hub_id": params["hub_id"],
        "user_id": user_id,
        "title": params["title"],
        "priority": params.get("priority", "low"),
        "status": params.get("status", "todo"),
    }).execute()

    return {"type": "task_created", "task": result.data[0] if result.data else {}}