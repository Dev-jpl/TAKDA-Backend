import os
import json
import re
from datetime import datetime, timezone, timedelta
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from database import supabase
from services.agent_graph.state import AgentState
from services.agent_graph.tools import AGENT_TOOLS
from services.ai import get_ai_response_async
from services.aly_memory import extract_and_store_memories
from config import ASSISTANT_NAME

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama")
MAIN_MODEL = os.getenv("MAIN_MODEL", "qwen2.5:7b")
FAST_MODEL = os.getenv("FAST_MODEL", "qwen2.5:3b")
MEMORY_TABLE = os.getenv("AGENT_MEMORY_TABLE", "agent_memory")

# Maps LangChain tool name → action_type used by execute_proposal
TOOL_TO_ACTION = {
    "create_task": "CREATE_TASK",
    "update_task": "UPDATE_TASK",
    "create_event": "CREATE_EVENT",
    "log_expense": "LOG_EXPENSE",
    "log_food": "LOG_FOOD",
    "save_to_vault": "SAVE_TO_VAULT",
    "save_report": "SAVE_REPORT",
    "create_space": "CREATE_SPACE",
    "create_hub": "CREATE_HUB",
}


def _build_proposal(tool_name: str, tool_args: dict, hubs: list) -> dict:
    """Converts a tool call into a human-readable proposal (not yet executed)."""
    from datetime import datetime as _dt
    action_type = TOOL_TO_ACTION.get(tool_name, tool_name.upper())

    if tool_name == "create_task":
        hub_name = tool_args.get("hub_name", "your hub")
        priority = tool_args.get("priority", "low")
        label = tool_args.get("title", "New task")
        due = f" · due {tool_args['due_date']}" if tool_args.get("due_date") else ""
        impact = f"Add '{label}' to {hub_name} · {priority} priority{due}"

    elif tool_name == "update_task":
        label = tool_args.get("title") or f"task"
        changes = []
        if tool_args.get("status"):   changes.append(f"mark as {tool_args['status']}")
        if tool_args.get("priority"): changes.append(f"priority → {tool_args['priority']}")
        if tool_args.get("title"):    changes.append(f"rename to '{tool_args['title']}'")
        impact = ", ".join(changes) or "update task"

    elif tool_name == "create_event":
        label = tool_args.get("title", "New event")
        start = tool_args.get("start_time", "")
        try:
            dt = _dt.fromisoformat(start)
            impact = f"Schedule '{label}' on {dt.strftime('%b %d at %I:%M %p')}"
        except Exception:
            impact = f"Schedule '{label}'" + (f" on {start}" if start else "")

    elif tool_name == "log_expense":
        amount = tool_args.get("amount", 0)
        merchant = tool_args.get("merchant", "unknown")
        currency = tool_args.get("currency", "PHP")
        label = f"{currency} {float(amount):.2f} at {merchant}"
        impact = f"Log expense: {label}"

    elif tool_name == "log_food":
        food = tool_args.get("food_name", "food")
        cals = tool_args.get("calories")
        meal_type = tool_args.get("meal_type", "meal")
        label = food
        impact = f"Log {meal_type}: {food}" + (f" · {cals} kcal" if cals else "")

    elif tool_name == "save_to_vault":
        content = tool_args.get("content", "")
        label = (content[:40] + "...") if len(content) > 40 else content
        impact = "Save to vault for later sorting"

    elif tool_name == "save_report":
        label = tool_args.get("title", "Report")
        impact = f"Save report: '{label}'"

    elif tool_name == "create_space":
        label = tool_args.get("name", "New space")
        impact = f"Create space '{label}'"

    elif tool_name == "create_hub":
        label = tool_args.get("name", "New hub")
        space_name = tool_args.get("space_name", "")
        impact = f"Create hub '{label}'" + (f" in {space_name}" if space_name else "")

    else:
        label = tool_name
        impact = f"Perform: {tool_name}"

    # Strip injected fields from data so frontend doesn't resend them
    data = {k: v for k, v in tool_args.items() if k not in ("user_id", "session_id")}

    return {
        "type": "proposal",
        "status": "proposed",
        "action_type": action_type,
        "label": label,
        "impact": impact,
        "data": data,
    }

def _get_system_prompt() -> str:
    now_utc = datetime.now(timezone.utc)
    now_pht = now_utc + timedelta(hours=8)
    now_str = now_pht.strftime("%A, %B %-d, %Y at %-I:%M %p (PHT)")
    return f"""You are {ASSISTANT_NAME} — a warm, sharp personal companion inside TAKDA.
You have full visibility into the user's world: their tasks, calendar events, spaces, hubs, \
annotations, knowledge documents, fitness activity, and connected integrations.
Speak like a trusted friend who gets things done — concise, real, never corporate or robotic.
Reference specific data from context when relevant. If something isn't in context, say so briefly.
Always respond in the same language the user writes in.

Tool guidance:
- Use log_expense when the user mentions prices, costs, spending money, or explicitly says "expense tracker" / "budget". Numbers alongside items = prices.
- Use log_food ONLY for calorie/nutrition tracking. If food items have prices attached, use log_expense.
- When a user lists multiple items with amounts (e.g. "chicken 79, rice 15"), call log_expense once per item.

Today is {now_str}."""


def get_main_model():
    if AI_PROVIDER == "ollama":
        base_url = OLLAMA_BASE_URL
        api_key = "ollama"
        model = MAIN_MODEL
    else:
        base_url = OPENROUTER_BASE_URL
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = "anthropic/claude-sonnet-4-6"

    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        streaming=True,
        temperature=0.3,
    ).bind_tools(AGENT_TOOLS)


def get_fast_model():
    if AI_PROVIDER == "ollama":
        base_url = OLLAMA_BASE_URL
        api_key = "ollama"
        model = FAST_MODEL
    else:
        base_url = OPENROUTER_BASE_URL
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = "meta-llama/llama-3.1-8b-instruct:free"

    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        streaming=False,
        temperature=0.1,
    )


# ── Node 1: Load context ──────────────────────────────────────────────────────
async def node_load_context(state: AgentState) -> AgentState:
    user_id = state["user_id"]
    hub_ids = state.get("hub_ids", [])

    tasks, hubs, spaces, memories = [], [], [], []
    events, annotations, knowledge_docs, strava_activities, integrations = [], [], [], [], []

    # Tasks — active only
    try:
        q = supabase.table("tasks").select("id,title,status,priority,hub_id,due_date") \
            .eq("user_id", user_id).neq("status", "done").limit(20)
        if hub_ids:
            q = q.in_("hub_id", hub_ids)
        tasks = q.execute().data or []
    except Exception as e:
        print(f"[node_load_context] tasks error: {e}")

    # Hubs with parent space name
    try:
        q = supabase.table("hubs").select("id,name,space_id,spaces(name)") \
            .eq("user_id", user_id)
        if hub_ids:
            q = q.in_("id", hub_ids)
        raw = q.execute().data or []
        hubs = [{"id": h["id"], "name": h["name"],
                 "space_name": (h.get("spaces") or {}).get("name", "")} for h in raw]
    except Exception as e:
        print(f"[node_load_context] hubs error: {e}")

    # Spaces
    try:
        raw = supabase.table("spaces").select("id,name,description") \
            .eq("user_id", user_id).limit(20).execute().data or []
        spaces = [{"id": s["id"], "name": s["name"], "description": s.get("description", "")} for s in raw]
    except Exception as e:
        print(f"[node_load_context] spaces error: {e}")

    # Memories
    try:
        memories = supabase.table(MEMORY_TABLE) \
            .select("content,memory_type") \
            .eq("user_id", user_id) \
            .order("last_reinforced", desc=True) \
            .limit(8).execute().data or []
    except Exception as e:
        print(f"[node_load_context] memories error: {e}")

    # Calendar events — look back 12h to catch ongoing and today's early events (timezone buffer)
    try:
        now = datetime.now(timezone.utc)
        lookback = (now - timedelta(hours=12)).isoformat()
        week_out = (now + timedelta(days=7)).isoformat()
        raw = supabase.table("events") \
            .select("id,title,start_at,end_at,location,description") \
            .eq("user_id", user_id) \
            .gte("start_at", lookback) \
            .lte("start_at", week_out) \
            .order("start_at") \
            .limit(40).execute().data or []
        events = [{"title": e["title"], "start": e["start_at"],
                   "end": e.get("end_at"), "location": e.get("location")} for e in raw]
    except Exception as e:
        print(f"[node_load_context] events error: {e}")

    # Annotations — recent across user's hubs
    try:
        user_hub_ids = [h["id"] for h in hubs] if hubs else []
        if user_hub_ids:
            raw = supabase.table("annotations") \
                .select("id,content,category,hub_id") \
                .in_("hub_id", user_hub_ids) \
                .order("created_at", desc=True) \
                .limit(10).execute().data or []
            hub_map = {h["id"]: h["name"] for h in hubs}
            annotations = [{"content": a["content"], "category": a["category"],
                            "hub": hub_map.get(a["hub_id"], "")} for a in raw]
    except Exception as e:
        print(f"[node_load_context] annotations error: {e}")

    # Knowledge documents — titles only (content is too large)
    try:
        raw = supabase.table("documents") \
            .select("id,title,source_type") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .limit(15).execute().data or []
        knowledge_docs = [{"id": d["id"], "title": d["title"], "type": d.get("source_type", "")} for d in raw]
    except Exception as e:
        print(f"[node_load_context] knowledge_docs error: {e}")

    # Strava — recent activities (if connected)
    try:
        raw = supabase.table("strava_activities") \
            .select("sport_type,name,distance_meters,moving_time_seconds,start_date") \
            .eq("user_id", user_id) \
            .order("start_date", desc=True) \
            .limit(15).execute().data or []
        strava_activities = [
            {
                "sport": a["sport_type"],
                "name": a.get("name", ""),
                "distance_km": round(a.get("distance_meters", 0) / 1000, 1),
                "duration_min": round(a.get("moving_time_seconds", 0) / 60),
                # Convert UTC → PHT (UTC+8) for display
                "date": (
                    (datetime.fromisoformat((a["start_date"] or "").replace("Z", "+00:00"))
                     + timedelta(hours=8)).strftime("%Y-%m-%d")
                    if a.get("start_date") else ""
                ),
            }
            for a in raw
        ]
    except Exception as e:
        print(f"[node_load_context] strava error: {e}")

    # Connected integrations (which ones are linked)
    try:
        raw = supabase.table("user_integrations") \
            .select("provider") \
            .eq("user_id", user_id) \
            .execute().data or []
        integrations = [r["provider"] for r in raw]
    except Exception as e:
        print(f"[node_load_context] integrations error: {e}")

    return {
        **state,
        "tasks": tasks,
        "hubs": hubs,
        "spaces": spaces,
        "memories": memories,
        "events": events,
        "annotations": annotations,
        "knowledge_docs": knowledge_docs,
        "strava_activities": strava_activities,
        "integrations": integrations,
        "docs_text": "",
        "tool_results": [],
        "actions": [],
        "needs_clarification": False,
        "clarification_question": "",
    }


# ── Node 2: Classify intent (fast — Gemini via existing ai.py) ────────────────
async def node_classify_intent(state: AgentState) -> AgentState:
    history = state.get("history", [])
    history_text = "\n".join([
        f"{m['role']}: {m['content'][:100]}" for m in history[-4:]
    ]) if history else ""

    prompt = f"""Classify this message into one or more intents.

Intents:
- TASK: create, update, delete, or ask about tasks
- CALENDAR: create, update, delete, or ask about events
- EXPENSE: log or ask about spending
- FOOD: log or ask about meals/nutrition
- REPORT: generate or ask for a report
- KNOWLEDGE: ask about documents or knowledge base
- BRIEFING: ask for a summary of their day, week, progress, or any data overview
- VAULT: save something for later without specifying where
- SPACE: create or organize spaces/hubs
- CHAT: general conversation, reflection, opinions, casual questions
- CLARIFY: user wants a SPECIFIC action (create/update/delete) but is missing required details

Rules:
- CLARIFY only when the user clearly wants to DO something but is missing required fields (e.g. "add a task" with no title)
- Reflective/review questions ("how am I doing", "how is my X journey", "what have I done this week") → BRIEFING
- Questions about specific data ("show me my strava", "what tasks do I have") → use the matching intent (TASK, BRIEFING, etc.)
- Default to CHAT for anything conversational

Return ONLY valid JSON: {{"intents":["BRIEFING"],"primary":"BRIEFING"}}

Recent conversation:
{history_text}

Message: "{state['user_message']}"
"""
    try:
        response = await get_ai_response_async(
            "You classify user intent. Return JSON only.", prompt
        )
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return {**state, "intent": data.get("primary", "CHAT"),
                    "intents": data.get("intents", ["CHAT"])}
    except Exception as e:
        print(f"[node_classify_intent] error: {e}")

    return {**state, "intent": "CHAT", "intents": ["CHAT"]}


# ── Node 3: Check clarification (fast — Gemini) ───────────────────────────────
async def node_check_clarification(state: AgentState) -> AgentState:
    if state.get("intent") != "CLARIFY":
        return {**state, "needs_clarification": False}

    hubs_text = "\n".join([f"- {h['name']} [id:{h['id']}]"
                           for h in state.get("hubs", [])])
    prompt = f"""The user wants to do something but details are missing.
Available hubs: {hubs_text}
User message: "{state['user_message']}"

Ask ONE specific question to get the missing info. Be brief and warm. Max 1 sentence."""

    try:
        question = await get_ai_response_async(
            "You ask for missing information. One question only.", prompt
        )
        return {**state, "needs_clarification": True,
                "clarification_question": question.strip(),
                "response": question.strip()}
    except Exception as e:
        print(f"[node_check_clarification] error: {e}")
        return {**state, "needs_clarification": False}


# ── Node 4: Main response ─────────────────────────────────────────────────────
async def node_respond(state: AgentState) -> AgentState:
    def _fmt_list(items, fmt_fn, empty="None."):
        return "\n".join(fmt_fn(i) for i in items) if items else empty

    tasks_text = _fmt_list(
        state.get("tasks", []),
        lambda t: f"- [{t.get('priority','low')}] {t['title']} ({t['status']})"
                  + (f" · due {t['due_date']}" if t.get("due_date") else "")
                  + f" [id:{t['id']}]",
        "No active tasks.",
    )

    hubs_text = _fmt_list(
        state.get("hubs", []),
        lambda h: f"- {h['name']}" + (f" (in {h['space_name']})" if h.get("space_name") else "")
                  + f" [id:{h['id']}]",
        "No hubs.",
    )

    spaces_text = _fmt_list(
        state.get("spaces", []),
        lambda s: f"- {s['name']} [id:{s['id']}]" + (f": {s['description']}" if s.get("description") else ""),
        "No spaces.",
    )

    events_text = _fmt_list(
        state.get("events", []),
        lambda e: f"- {e['title']} @ {(e['start'] or '')[:16].replace('T', ' ')}"
                  + (f" [{e['location']}]" if e.get("location") else ""),
        "No upcoming events.",
    )

    annotations_text = _fmt_list(
        state.get("annotations", []),
        lambda a: f"- [{a['category']}] {a['content'][:80]}" + (f" (hub: {a['hub']})" if a.get("hub") else ""),
        "No annotations.",
    )

    knowledge_text = _fmt_list(
        state.get("knowledge_docs", []),
        lambda d: f"- {d['title']}" + (f" ({d['type']})" if d.get("type") else ""),
        "No documents.",
    )

    strava_text = _fmt_list(
        state.get("strava_activities", []),
        lambda a: f"- {a['date']} {a['sport']}: {a['name']} · {a['distance_km']}km · {a['duration_min']}min",
        "No recent Strava activity.",
    )

    integrations = state.get("integrations", [])
    integrations_text = ", ".join(integrations) if integrations else "None connected."

    memory_text = _fmt_list(
        state.get("memories", []),
        lambda m: f"- {m['content']}",
        "Nothing yet.",
    )

    history_text = "\n".join([
        f"{m['role']}: {m['content'][:200]}" for m in state.get("history", [])[-6:]
    ])

    now_utc = datetime.now(timezone.utc)
    now_pht = now_utc + timedelta(hours=8)
    now_str = now_pht.strftime("%A, %B %-d, %Y at %-I:%M %p (PHT)")

    context = f"""=== USER CONTEXT ===

Current date and time: {now_str}

Tasks (active):
{tasks_text}

Spaces:
{spaces_text}

Hubs:
{hubs_text}

Calendar (next 7 days):
{events_text}

Annotations (recent):
{annotations_text}

Knowledge documents:
{knowledge_text}

Strava (recent activity):
{strava_text}

Connected integrations: {integrations_text}

What you know about this user:
{memory_text}

=== CONVERSATION ===
{history_text}

User: {state['user_message']}"""

    messages = [SystemMessage(content=_get_system_prompt()), HumanMessage(content=context)]
    model = get_main_model()
    proposals = []
    response_text = ""

    try:
        response = await model.ainvoke(messages)
        response_text = response.content or ""

        if hasattr(response, 'tool_calls') and response.tool_calls:
            hubs = state.get("hubs", [])
            for tc in response.tool_calls:
                tool_name = tc["name"]
                tool_args = tc.get("args", {})
                proposals.append(_build_proposal(tool_name, tool_args, hubs))

            # Generate human-friendly proposal text using fast model
            if proposals:
                proposals_summary = "\n".join([
                    f"- {p['impact']}" for p in proposals
                ])
                proposal_prompt = f"""You are about to do the following for the user:
{proposals_summary}

Write a brief, warm message (1-2 sentences) telling them what you're about to do and asking if they want to proceed.
Be natural and friendly. Do not use bullet points or headers. Do not mention JSON or technical terms."""
                response_text = await get_ai_response_async(AGENT_SYSTEM, proposal_prompt)

    except Exception as e:
        print(f"[node_respond] error: {e}")
        response_text = "Something went wrong. Try again?"

    return {**state, "response": response_text,
            "tool_results": [], "actions": proposals}


# ── Node 5: Extract memories (reuses existing aly_memory.py) ─────────────────
async def node_extract_memories(state: AgentState) -> AgentState:
    try:
        conversation = (state.get("history", [])[-4:] +
                        [{"role": "assistant", "content": state.get("response", "")}])
        await extract_and_store_memories(state["user_id"], conversation)
    except Exception as e:
        print(f"[node_extract_memories] error: {e}")
    return state  # fire and forget
