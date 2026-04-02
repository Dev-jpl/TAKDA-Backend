import re
import json
from database import supabase
from services.ai import get_streaming_ai_response, search_chunks
from services.agents.coordinator import AgentCoordinator
from services.agents.task_agent import run_task_agent_stream, execute_task_action
from services.agents.report_agent import run_report_agent_stream
from services.agents.calendar_agent import run_calendar_agent_stream
from services.agents.quiz_agent import generate_quiz_stream

CHAT_PROMPT = """You are Kalay — a warm, sharp AI companion inside TAKDA, a personal life OS.

You know the user's tasks, documents, and spaces.
You are concise, direct, and helpful. Not chatty.
You speak like a smart friend, not a corporate assistant.

If the user asks about their data, use the context provided.
If you don't have enough context, say so briefly and ask what they need.
Never make up tasks, events, or data that aren't in the context.
"""

async def build_context(user_id: str, hub_ids: list, space_ids: list, message: str) -> dict:
    context = {"tasks": [], "hubs": [], "docs_text": "", "spaces": []}

    if hub_ids:
        tasks_res = supabase.table("tasks") \
            .select("id, title, status, priority, hub_id") \
            .in_("hub_id", hub_ids) \
            .neq("status", "done") \
            .limit(20) \
            .execute()
        context["tasks"] = tasks_res.data or []

        hubs_res = supabase.table("hubs") \
            .select("id, name, space_id, spaces(name)") \
            .in_("id", hub_ids) \
            .execute()
        context["hubs"] = [
            {
                "id": h["id"],
                "name": h["name"],
                "space_name": h.get("spaces", {}).get("name", ""),
            }
            for h in (hubs_res.data or [])
        ]

    if space_ids:
        spaces_res = supabase.table("spaces") \
            .select("id, name, category") \
            .in_("id", space_ids) \
            .execute()
        context["spaces"] = spaces_res.data or []

    # Semantic search only for questions or longer messages
    if len(message.split()) > 3:
        doc_res = supabase.table("documents") \
            .select("id") \
            .eq("user_id", user_id) \
            .execute()
        doc_ids = [d["id"] for d in (doc_res.data or [])]
        if doc_ids:
            chunks = await search_chunks(message, user_id, document_ids=doc_ids, limit=4)
            if chunks:
                context["docs_text"] = "\n".join([f"[{i+1}] {c['content']}" for i, c in enumerate(chunks)])

    return context


async def process_kalay_chat_stream(
    user_id: str,
    session_id: str,
    message: str,
    space_ids: list,
    hub_ids: list,
    conversation_history: list = []
):
    # 1. Build context
    context = await build_context(user_id, hub_ids, space_ids, message)

    tasks_text = "\n".join([
        f"- [{t['status']}] {t['title']} (priority: {t['priority']}, hub: {t['hub_id']})"
        for t in context["tasks"]
    ]) or "No active tasks."

    hubs_text = "\n".join([
        f"- {h['name']} (id: {h['id']}, space: {h['space_name']})"
        for h in context["hubs"]
    ]) or "No hubs selected."

    # 2. Classify intent (with history for better accuracy)
    classification = await AgentCoordinator.classify_intent(message, conversation_history)
    intents = classification.get("intents", ["CHAT"])
    primary = classification.get("primary", "CHAT")

    # 3. Route to primary agent — yield its stream
    if primary == "TASK":
        async for chunk in run_task_agent_stream(message, context["hubs"], conversation_history):
            yield chunk

    elif primary == "REPORT":
        async for chunk in run_report_agent_stream(
            message, tasks_text, context["docs_text"], conversation_history
        ):
            yield chunk

    elif primary == "CALENDAR":
        async for chunk in run_calendar_agent_stream(message, conversation_history):
            yield chunk

    elif primary == "QUIZ":
        async for chunk in generate_quiz_stream(user_id, message, context["docs_text"]):
            yield chunk

    else:
        # CHAT fallback — Kalay with full context
        history_text = "\n".join([
            f"{m['role']}: {m['content'][:200]}"
            for m in (conversation_history[-6:] if conversation_history else [])
        ])

        user_prompt = f"""Context:
Active tasks:
{tasks_text}

Available hubs:
{hubs_text}

Relevant knowledge:
{context['docs_text'] or 'None found.'}

Conversation history:
{history_text}

User: {message}"""

        async for chunk in get_streaming_ai_response(CHAT_PROMPT, user_prompt):
            yield chunk


async def parse_and_execute_actions(
    user_id: str,
    session_id: str,
    full_text: str,
    space_ids: list,
    hub_ids: list
) -> tuple[str, list]:
    actions = []
    clean_text = full_text

    # Find all action tags
    tag_pattern = re.compile(r'\[(CREATE_TASK|UPDATE_TASK|CREATE_EVENT|SAVE_REPORT|QUIZ_DATA)[:\s]([^\]]*)\]', re.DOTALL)

    for match in tag_pattern.finditer(full_text):
        tag_type = match.group(1)
        tag_content = match.group(2)
        clean_text = clean_text.replace(match.group(0), "").strip()

        if tag_type == "CREATE_TASK":
            result = await execute_task_action(tag_content, user_id)
            if result.get("task"):
                t = result["task"]
                actions.append({
                    "type": "task_created",
                    "label": t.get("title", "Task"),
                    "priority": t.get("priority", "low"),
                    "status": t.get("status", "todo"),
                    "id": t.get("id"),
                    "hub_id": t.get("hub_id"),
                })

        elif tag_type == "UPDATE_TASK":
            params = {}
            for m in re.finditer(r'(\w+)="([^"]*)"', tag_content):
                params[m.group(1)] = m.group(2)
            if params.get("id"):
                updates = {k: v for k, v in params.items() if k != "id"}
                supabase.table("tasks").update(updates).eq("id", params["id"]).execute()
                actions.append({"type": "task_updated", "id": params["id"], **updates})

        elif tag_type == "CREATE_EVENT":
            params = {}
            for m in re.finditer(r'(\w+)="([^"]*)"', tag_content):
                params[m.group(1)] = m.group(2)
            actions.append({"type": "event_created", **params})

        elif tag_type == "SAVE_REPORT":
            params = {}
            for m in re.finditer(r'(\w+)="([^"]*)"', tag_content):
                params[m.group(1)] = m.group(2)
            report_content = full_text.split("[SAVE_REPORT")[0].strip()
            supabase.table("kalay_outputs").insert({
                "user_id": user_id,
                "session_id": session_id,
                "type": params.get("type", "report"),
                "title": params.get("title", "Untitled"),
                "content": report_content,
                "space_ids": space_ids,
                "hub_ids": hub_ids,
            }).execute()
            actions.append({
                "type": "report_saved",
                "label": params.get("title", "Report"),
                "output_type": params.get("type", "report"),
            })

    return clean_text, actions