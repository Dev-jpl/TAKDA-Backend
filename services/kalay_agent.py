import json
import re
from database import supabase
from services.ai import get_ai_response, get_streaming_ai_response, search_chunks
from services.agents.coordinator import AgentCoordinator
from services.agents.quiz_agent import generate_quiz_stream, save_quiz_to_db
from services.agents.report_agent import generate_report_stream
from services.agents.task_agent import extract_tasks_stream
from services.agents.space_agent import manage_spaces_stream
from services.agents.calendar_agent import generate_calendar_stream

async def process_kalay_chat_stream(user_id: str, session_id: str, message: str, space_ids: list[str], hub_ids: list[str]):
    # 1. Fetch Context (Tasks, Documents, and Names)
    tasks_context = ""
    if hub_ids:
        tasks_res = supabase.table("tasks").select("title, status, priority, hub_id").in_("hub_id", hub_ids).execute()
        if tasks_res.data:
            tasks_context = "CURRENT TASKS:\n" + "\n".join([f"- {t['title']} ({t['status']})" for t in tasks_res.data])

    spaces_info = ""
    if space_ids:
        spaces_res = supabase.table("spaces").select("id, name").in_("id", space_ids).execute()
        if spaces_res.data:
            spaces_info = "EXISTING SPACES:\n" + "\n".join([f"- {s['name']} (ID: {s['id']})" for s in spaces_res.data])

    docs_context = ""
    if message.strip().endswith("?") or len(message.split()) > 4:
        doc_res = supabase.table("documents").select("id").eq("user_id", user_id).execute()
        doc_ids = [d["id"] for d in doc_res.data] if doc_res.data else []
        if doc_ids:
            chunks = await search_chunks(message, user_id, document_ids=doc_ids, limit=5)
            if chunks:
                docs_context = "\nRELEVANT KNOWLEDGE:\n" + "\n".join([f"[{i+1}] {c['content']}" for i, c in enumerate(chunks)])

    # 2. Classify Intent
    classification = await AgentCoordinator.classify_intent(message)
    intent = classification.get("intent", "CONVERSATION")
    
    # 3. Route to Sub-Agent Stream
    if intent == "QUIZ":
        async for chunk in generate_quiz_stream(user_id, message, docs_context):
            yield chunk
    elif intent == "REPORT":
        async for chunk in generate_report_stream(user_id, message, docs_context, tasks_context):
            yield chunk
    elif intent == "TASK":
        async for chunk in extract_tasks_stream(user_id, message, spaces_info):
            yield chunk
    elif intent == "SPACE_MANAGEMENT":
        async for chunk in manage_spaces_stream(user_id, message, spaces_info):
            yield chunk
    elif intent == "CALENDAR":
        async for chunk in generate_calendar_stream(user_id, message):
            yield chunk
    else:
        # Standard Conversation Fallback
        system_prompt = f"""You are Kalay, the high-agency AI companion for TAKDA.
CONTEXT:
{tasks_context}
{docs_context}
{spaces_info}

If the user wants a task, report, quiz, or space management, you would normally trigger a sub-agent, 
but for now, just chat professionally.
"""
        user_prompt = f"User: {message}\nKalay:"
        async for chunk in get_streaming_ai_response(system_prompt, user_prompt):
            yield chunk

async def parse_and_execute_actions(user_id: str, session_id: str, full_text: str, space_ids: list[str], hub_ids: list[str]):
    actions = []
    last_created_space_id = None

    # 1. Space Creation (Process first for chaining)
    space_match = re.search(r'\[CREATE_SPACE:\s*name="([^"]+)",\s*icon="([^"]+)",\s*color="([^"]+)"\]', full_text)
    if space_match:
        name, icon, color = space_match.groups()
        res = supabase.table("spaces").insert({"user_id": user_id, "name": name, "icon": icon, "color": color}).execute()
        if res.data:
            last_created_space_id = res.data[0]["id"]
            actions.append({"type": "space_created", "label": name, "id": last_created_space_id})

    # 2. Hub Creation (Handle PENDING_SPACE)
    hub_matches = re.finditer(r'\[CREATE_HUB:\s*space_id="([^"]+)",\s*name="([^"]+)",\s*icon="([^"]+)"\]', full_text)
    for match in hub_matches:
        space_id, name, icon = match.groups()
        target_space_id = last_created_space_id if space_id == "PENDING_SPACE" else space_id
        if target_space_id:
            res = supabase.table("hubs").insert({"user_id": user_id, "space_id": target_space_id, "name": name, "icon": icon}).execute()
            if res.data:
                actions.append({"type": "hub_created", "label": name, "id": res.data[0]["id"], "space_id": target_space_id})

    # 3. Task Creation
    task_match = re.search(r'\[CREATE_TASK:\s*title="([^"]+)",\s*priority="([^"]+)",\s*hub_id="([^"]+)"\]', full_text)
    if task_match:
        title, priority, hub_id = task_match.groups()
        res = supabase.table("tasks").insert({"user_id": user_id, "hub_id": hub_id, "title": title, "priority": priority, "status": "todo"}).execute()
        if res.data:
            actions.append({"type": "task_created", "label": title, "id": res.data[0]["id"]})

    # 4. Event Creation
    event_match = re.search(r'\[CREATE_EVENT:\s*title="([^"]+)",\s*start="([^"]+)",\s*end="([^"]+)",\s*desc="([^"]*)",\s*all_day=(true|false),\s*hub_id="([^"]*)"\]', full_text)
    if event_match:
        title, start, end, desc, all_day, h_id = event_match.groups()
        event_dict = {
            "user_id": user_id,
            "title": title,
            "start_time": start,
            "end_time": end,
            "description": desc or None,
            "is_all_day": all_day == "true",
            "hub_id": h_id if h_id and h_id != "null" else None
        }
        res_e = supabase.table("events").insert(event_dict).execute()
        if res_e.data:
            actions.append({"type": "event_created", "label": title, "id": res_e.data[0]["id"]})

    # 5. Quiz Saving (Look for [QUIZ_DATA]...[/QUIZ_DATA])
    quiz_match = re.search(r'\[QUIZ_DATA\](.*?)\[/QUIZ_DATA\]', full_text, re.DOTALL)
    if quiz_match:
        try:
            quiz_json = json.loads(quiz_match.group(1).strip())
            # Use 'New Quiz' as default title
            res_q = supabase.table("kalay_quizzes").insert({"user_id": user_id, "session_id": session_id, "title": "New Quiz"}).execute()
            if res_q.data:
                q_id = res_q.data[0]["id"]
                for q in quiz_json:
                    supabase.table("kalay_quiz_questions").insert({
                        "quiz_id": q_id,
                        "type": q.get("type", "multiple_choice"),
                        "question": q.get("question", ""),
                        "options": q.get("options", []),
                        "correct_answer": str(q.get("correct_answer", "")),
                        "explanation": q.get("explanation", "")
                    }).execute()
                actions.append({"type": "quiz_generated", "label": "New Quiz Engine", "id": q_id})
        except Exception as e:
            print(f"Quiz save error: {e}")
    clean_reply = re.sub(r'\[(?:CREATE_TASK|GENERATE_REPORT|CREATE_SPACE|CREATE_HUB|CREATE_EVENT|QUIZ_DATA|/QUIZ_DATA):.*?\]', '', full_text).strip()
    return clean_reply, actions
