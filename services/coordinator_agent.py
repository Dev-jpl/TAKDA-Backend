import re
import json
from datetime import datetime, timedelta
from typing import AsyncGenerator
from services.agents.coordinator import AgentCoordinator
from services.agents.base import BASE_IDENTITY
from config import ASSISTANT_NAME
from database import supabase
from services.agents.brainstorm_agent import run_brainstorm_logic



# --- Dedicated Toolsets ---

TASK_PROMPT = f"""{BASE_IDENTITY} 
MISSION: You are the Task Specialist. Coordinate mission-critical actions with absolute precision.
Tools:
[PROPOSE_CREATE_TASK: title="Title" hub_id="<UUID>" priority="low|medium|high"]
[PROPOSE_UPDATE_TASK: id="<UUID>" title="New Name" status="todo|done"]

RULE: If Hub or Priority is missing, stop and ASK for them. OMIT attributes if values are unknown.
"""

EVENT_PROMPT = f"""{BASE_IDENTITY}
MISSION: You are the Calendar Specialist. Schedule missions and manage time with high-density.
Tools:
[PROPOSE_CREATE_EVENT: title="Name" start_time="ISO" end_time="ISO" hub_id="ID" location="Plain Text"]

RULE: If start_time is missing, stop and ASK for it. end_time and location are optional.
RULE: If the mission context implies a specific Hub from the context, always include its hub_id.
"""

SPACE_PROMPT = f"""{BASE_IDENTITY}
MISSION: You are the Architectural Specialist. Organize hubs and spaces for maximum focus.
Tools:
[PROPOSE_UPDATE_HUB: id="<UUID>" name="New Name" space_id="<UUID>"]
[PROPOSE_CREATE_HUB: name="Name" space_id="<UUID>"]
"""

CHAT_PROMPT = f"""{BASE_IDENTITY}
MISSION: Generic coordination and companion chat. Handle greetings and high-density knowledge extraction.
Tools:
[PROPOSE_SAVE_REPORT: title="Name" type="summary|brief|log"]
"""

REPORT_PROMPT = f"""{BASE_IDENTITY}
MISSION: You are the Analytics Specialist. Generate high-fidelity reports, summaries, and presentations for your coordination missions.
Tools:
[PROPOSE_SAVE_REPORT: title="Name" type="summary|brief|log"]
"""

QUIZ_PROMPT = f"""{BASE_IDENTITY}
MISSION: You are the Knowledge Specialist. Create high-intensity quizzes, flashcards, and learning materials from your mission logs.
Tools:
[QUIZ_DATA: title="Quiz Name" data="JSON"]
"""

KNOWLEDGE_PROMPT = f"""{BASE_IDENTITY}
MISSION: You are the Research Specialist. Answer questions and explore mission data with absolute technical clarity.
"""

async def process_coordinator_chat_stream(
    user_id: str, 
    message: str, 
    conversation_history: list = [],
    context: dict = {}
) -> AsyncGenerator[str, None]:
    """Main entry point for Aly chat logic with dedicated toolsets."""
    
    # 1. Classify Intent
    intent_data = await AgentCoordinator.classify_intent(message, conversation_history)
    primary = intent_data.get("primary", "CHAT")
    
    tasks_text = "\n".join([f"- {t['title']} ({t['status']}) [id: {t['id']}]" for t in context.get("tasks", [])])
    hubs_text = "\n".join([f"- {h['name']} [id: {h['id']}]" for h in context.get("hubs", [])])

    # 2. Route to specialized logic
    if primary == "ARCHITECT":
        async for chunk in run_architect_logic(user_id, message):
            yield chunk

    elif primary == "CALENDAR":
        from services.agents.calendar_agent import run_calendar_logic
        async for chunk in run_calendar_logic(user_id, message, context):
            yield chunk

    elif primary == "SITREP":
        async for chunk in run_sitrep_logic(user_id):
            yield chunk

    elif primary == "CLEANER":
        async for chunk in run_cleaner_logic(user_id):
            yield chunk

    elif primary == "FOCUS":
        async for chunk in run_focus_logic(user_id, message, context):
            yield chunk

    elif primary == "CONSTITUTE":
        async for chunk in run_constitute_logic(user_id, context):
            yield chunk

    elif primary == "GUARD":
        async for chunk in run_guard_logic(user_id, message, context):
            yield chunk
            
    elif primary == "BRAINSTORM":
        async for chunk in run_brainstorm_logic(user_id, message, context):
            yield chunk

    elif primary == "CLARIFY":
        # Agent Looping — explicitly ask for missing data
        CLARIFY_PROMPT = f"""{BASE_IDENTITY}
The user wants to coordinate an action but essential details are missing.
Context:
Tasks: {tasks_text}
Hubs: {hubs_text}

MISSION: Be sharp and warm. Ask for the missing technical details directly. Do not coordinate the action yet.
"""
        async for chunk in get_streaming_ai_response(CLARIFY_PROMPT, message):
            yield chunk

    else:
        # Route CHAT intents to specialized toolset prompts if they match a specific module
        active_prompt = CHAT_PROMPT
        if primary == "TASK": active_prompt = TASK_PROMPT
        elif primary == "CALENDAR": active_prompt = EVENT_PROMPT
        elif primary == "SPACE": active_prompt = SPACE_PROMPT
        elif primary == "REPORT": active_prompt = REPORT_PROMPT
        elif primary == "QUIZ": active_prompt = QUIZ_PROMPT
        elif primary == "KNOWLEDGE": active_prompt = KNOWLEDGE_PROMPT
        elif primary == "KNOWLEDGE": active_prompt = KNOWLEDGE_PROMPT

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
{context.get('docs_text', 'None found.')}

Conversation history:
{history_text}

User: {message}"""

        async for chunk in get_streaming_ai_response(active_prompt, user_prompt):
            yield chunk

async def parse_and_propose_actions(
    user_id: str,
    session_id: str,
    full_text: str,
    space_ids: list,
    hub_ids: list
) -> tuple[str, list]:
    actions = []
    clean_text = full_text
    tag_pattern = re.compile(r'\[(PROPOSE_CREATE_TASK|PROPOSE_UPDATE_TASK|PROPOSE_CREATE_EVENT|PROPOSE_UPDATE_EVENT|PROPOSE_DELETE_EVENT|PROPOSE_CREATE_HUB|PROPOSE_UPDATE_HUB|PROPOSE_SAVE_REPORT|SAVE_REPORT|QUIZ_DATA|CREATE_TASK|UPDATE_TASK|CREATE_EVENT|GENERATE_IDEAS|PROPOSE_MIND_MAP)[:\s]([^\]]*)\]', re.DOTALL)

    for match in tag_pattern.finditer(full_text):
        tag_type = match.group(1)
        tag_content = match.group(2)
        clean_text = clean_text.replace(match.group(0), "").strip()

        # TASK TOOLS
        if tag_type in ["PROPOSE_CREATE_TASK", "CREATE_TASK"]:
            params = {}
            for m in re.finditer(r'(\w+)="([^"]*)"', tag_content):
                params[m.group(1)] = m.group(2)
            actions.append({
                "type": "proposal", "action_type": "CREATE_TASK", "label": params.get("title", "New Task"),
                "status": "proposed", "data": params, "impact": f"This will coordinate a new mission: '{params.get('title', 'Action')}'."
            })
        elif tag_type in ["PROPOSE_UPDATE_TASK", "UPDATE_TASK"]:
            params = {}
            for m in re.finditer(r'(\w+)="([^"]*)"', tag_content):
                params[m.group(1)] = m.group(2)
            actions.append({
                "type": "proposal", "action_type": "UPDATE_TASK", "label": f"Update {params.get('title', 'Task')}",
                "status": "proposed", "data": params, "impact": f"This will modify the parameters of mission: '{params.get('title', 'Action')}'."
            })
        
        # EVENT TOOLS
        elif tag_type in ["PROPOSE_CREATE_EVENT", "CREATE_EVENT"]:
            params = {}
            for m in re.finditer(r'(\w+)="([^"]*)"', tag_content):
                params[m.group(1)] = m.group(2)
            
            # Map the high-fidelity metadata for the UI and backend execution
            label = params.get("title", "New Event")
            if params.get("location"): label += f" @ {params.get('location')}"

            actions.append({
                "type": "proposal", 
                "action_type": "CREATE_EVENT", 
                "label": label,
                "status": "proposed", 
                "data": params, 
                "impact": f"This will schedule a new mission on your calendar: '{params.get('title', 'Event')}'."
            })
        elif tag_type == "PROPOSE_UPDATE_EVENT":
            params = {}
            for m in re.finditer(r'(\w+)="([^"]*)"', tag_content):
                params[m.group(1)] = m.group(2)
            actions.append({
                "type": "proposal", "action_type": "UPDATE_EVENT", "label": f"Update Event: {params.get('title', 'Mission')}",
                "status": "proposed", "data": params, "impact": "This will modify the metadata of your mission schedule."
            })
        elif tag_type == "PROPOSE_DELETE_EVENT":
            params = {}
            for m in re.finditer(r'(\w+)="([^"]*)"', tag_content):
                params[m.group(1)] = m.group(2)
            actions.append({
                "type": "proposal", "action_type": "DELETE_EVENT", "label": f"Cancel Mission Entry",
                "status": "proposed", "data": params, "impact": "This will permanently remove this mission log from your calendar."
            })

        # SPACE TOOLS
        elif tag_type in ["PROPOSE_CREATE_HUB", "PROPOSE_UPDATE_HUB"]:
             params = {}
             for m in re.finditer(r'(\w+)="([^"]*)"', tag_content):
                 params[m.group(1)] = m.group(2)
             actions.append({
                 "type": "proposal", "action_type": "MANAGE_SPACE", "label": params.get("name", "New Hub"),
                 "status": "proposed", "data": params, "impact": f"This will modify the architecture of your coordination spaces."
             })

        # REPORT TOOLS
        elif tag_type in ["PROPOSE_SAVE_REPORT", "SAVE_REPORT"]:
            params = {}
            for m in re.finditer(r'(\w+)="([^"]*)"', tag_content):
                params[m.group(1)] = m.group(2)
            
            content_start = full_text.find(match.group(0))
            report_content = full_text[:content_start].strip()
            
            # Pack all necessary data for the execution endpoint
            params["content"] = report_content
            params["session_id"] = session_id
            params["space_ids"] = space_ids
            params["hub_ids"] = hub_ids

            actions.append({
                "type": "proposal", 
                "action_type": "SAVE_REPORT", 
                "label": f"Save {params.get('type', 'report')}: {params.get('title', 'Report')}",
                "status": "proposed", 
                "data": params, 
                "impact": "This will coordinate a new mission log in your persistent knowledge base."
            })

        # BRAINSTORM TOOLS
        elif tag_type == "GENERATE_IDEAS":
            params = {}
            for m in re.finditer(r'(\w+)="([^"]*)"', tag_content):
                params[m.group(1)] = m.group(2)
            actions.append({
                "type": "proposal", "action_type": "GENERATE_IDEAS", "label": f"Brainstorm: {params.get('topic', 'Ideas')}",
                "status": "proposed", "data": params, "impact": "This will expand your concepts into a high-fidelity list."
            })
        elif tag_type == "PROPOSE_MIND_MAP":
            params = {}
            for m in re.finditer(r'(\w+)="([^"]*)"', tag_content):
                params[m.group(1)] = m.group(2)
            actions.append({
                "type": "proposal", "action_type": "MIND_MAP", "label": f"Structural Map: {params.get('title', 'Concept')}",
                "status": "proposed", "data": params, "impact": "This will architect a visual structure for your mission area."
            })

    return clean_text, actions

async def generate_session_title(conversation_history: list) -> str:
    history_snippet = "\n".join([f"{m['role']}: {m['content'][:100]}" for m in conversation_history[-3:]])
    system = f"You are {ASSISTANT_NAME}'s summarizer. Create a 3-5 word catchy mission title. NO quotes, NO filler."
    title = ""
    async for chunk in get_streaming_ai_response(system, history_snippet):
        title += chunk
    return title.strip().replace('"', '')

async def get_streaming_ai_response(system: str, prompt: str) -> AsyncGenerator[str, None]:
    from services.ai import get_streaming_ai_response as stream_ai
    async for chunk in stream_ai(system, prompt):
        yield chunk

async def run_architect_logic(user_id: str, message: str):
    hubs_res = supabase.table("hubs").select("id, name, space_id").eq("user_id", user_id).execute()
    prompt = f"Current Hubs: {json.dumps(hubs_res.data or [])}\nUser Query: {message}"
    system = f"You are {ASSISTANT_NAME} Space Architect. Suggest structural optimizations (merges, splits)."
    async for chunk in get_streaming_ai_response(system, prompt):
        yield chunk

async def run_sitrep_logic(user_id: str):
    tasks_res = supabase.table("tasks").select("title, status, priority, due_date").eq("user_id", user_id).neq("status", "done").execute()
    events_res = supabase.table("events").select("title, start_time, end_time").eq("user_id", user_id).execute()
    prompt = f"Tasks: {json.dumps(tasks_res.data)}\nEvents: {json.dumps(events_res.data)}"
    system = f"You are {ASSISTANT_NAME} Mission Commander. Provide a high-fidelity SITREP using Markdown for structure. Use ### for headers, ** for importance, and bullet points for clarity. Summarize today's schedule, highlight priority missions, and identify any architectural bottlenecks."
    async for chunk in get_streaming_ai_response(system, prompt):
        yield chunk

async def run_cleaner_logic(user_id: str):
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    try:
        stale_res = supabase.table("hubs").select("id, name").eq("user_id", user_id).lt("updated_at", thirty_days_ago).execute()
        stale_hubs = stale_res.data or []
    except Exception:
        stale_res = supabase.table("hubs").select("id, name").eq("user_id", user_id).lt("created_at", thirty_days_ago).execute()
        stale_hubs = stale_res.data or []
    if not stale_hubs:
        yield "Your coordination environment is currently optimized. No stale hubs detected."
        return
    prompt = f"Stale Hubs: {json.dumps(stale_hubs)}"
    system = f"You are {ASSISTANT_NAME} Architectural Cleaner. Propose archiving these mission zones using Markdown for clarity."
    async for chunk in get_streaming_ai_response(system, prompt):
        yield chunk

async def run_focus_logic(user_id: str, message: str, context: dict):
    system = f"You are {ASSISTANT_NAME} Focus Guard. Identify the 3 most critical tasks for the user's requested focus and suggest a high-intensity path forward. Use ### for specific mission headers and ** for critical constraints."
    prompt = f"User Request: {message}\nTasks: {json.dumps(context.get('tasks', []))}"
    async for chunk in get_streaming_ai_response(system, prompt):
        yield chunk

async def run_brainstorm_logic(user_id: str, message: str, context: dict):
    system = f"You are {ASSISTANT_NAME} Cognitive Partner. Engage in high-fidelity brainstorming and ideation. Expand concepts, explore mission objectives, and propose creative architectural paths forward. Use Markdown for structure."
    prompt = f"Topic: {message}"
    async for chunk in get_streaming_ai_response(system, prompt):
        yield chunk

async def run_constitute_logic(user_id: str, context: dict):
    system = f"You are {ASSISTANT_NAME} Consolidator. Identify redundant or overlapping tasks and propose a high-fidelity merge using [PROPOSE_UPDATE_TASK] tags."
    prompt = f"Tasks: {json.dumps(context.get('tasks', []))}"
    async for chunk in get_streaming_ai_response(system, prompt):
        yield chunk

async def run_guard_logic(user_id: str, message: str, context: dict):
    system = f"You are {ASSISTANT_NAME} Calendar Guard. Scan for conflicts or overlaps in the schedule and propose adjustments."
    prompt = f"User Request: {message}\nEvents: {json.dumps(context.get('events', []))}"
    async for chunk in get_streaming_ai_response(system, prompt):
        yield chunk
