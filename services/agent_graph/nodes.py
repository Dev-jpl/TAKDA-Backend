import os
import json
import re
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from database import supabase
from services.agent_graph.state import AgentState
from services.agent_graph.tools import AGENT_TOOLS
from services.ai import get_ai_response_async
from services.aly_memory import extract_and_store_memories
from config import ASSISTANT_NAME

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
MAIN_MODEL = os.getenv("MAIN_MODEL", "qwen2.5-coder:7b")
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
        hub = next((h for h in hubs if h["id"] == tool_args.get("hub_id")), None)
        hub_name = hub["name"] if hub else "your hub"
        priority = tool_args.get("priority", "low")
        label = tool_args.get("title", "New task")
        impact = f"Add '{label}' to {hub_name} · {priority} priority"

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
        impact = f"Create hub '{label}'"

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

AGENT_SYSTEM = f"""You are {ASSISTANT_NAME} — a warm, sharp personal companion inside TAKDA.
You know the user's tasks, documents, calendar, and spending.
Speak like a trusted friend who gets things done.
Be concise. Be real. Never corporate or robotic.
If data isn't in context, say so briefly.
Always respond in the same language the user writes in."""


def get_main_model():
    model = ChatOpenAI(
        model=MAIN_MODEL,
        base_url=OLLAMA_BASE_URL,
        api_key="ollama",
        streaming=True,
        temperature=0.3,
    )
    return model.bind_tools(AGENT_TOOLS)


# ── Node 1: Load context ──────────────────────────────────────────────────────
async def node_load_context(state: AgentState) -> AgentState:
    user_id = state["user_id"]
    hub_ids = state.get("hub_ids", [])
    tasks, hubs, memories = [], [], []

    try:
        q = supabase.table("tasks").select("id,title,status,priority,hub_id,due_date") \
            .eq("user_id", user_id).neq("status", "done").limit(20)
        if hub_ids:
            q = q.in_("hub_id", hub_ids)
        tasks = q.execute().data or []
    except Exception as e:
        print(f"[node_load_context] tasks error: {e}")

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

    try:
        memories = supabase.table(MEMORY_TABLE) \
            .select("content,memory_type") \
            .eq("user_id", user_id) \
            .order("last_reinforced", desc=True) \
            .limit(8).execute().data or []
    except Exception as e:
        print(f"[node_load_context] memories error: {e}")

    return {
        **state,
        "tasks": tasks, "hubs": hubs, "memories": memories,
        "docs_text": "", "tool_results": [], "actions": [],
        "needs_clarification": False, "clarification_question": "",
    }


# ── Node 2: Classify intent (fast — Gemini via existing ai.py) ────────────────
async def node_classify_intent(state: AgentState) -> AgentState:
    history = state.get("history", [])
    history_text = "\n".join([
        f"{m['role']}: {m['content'][:100]}" for m in history[-4:]
    ]) if history else ""

    prompt = f"""Classify this message into one or more intents.
Intents: TASK | CALENDAR | EXPENSE | FOOD | REPORT | QUIZ | KNOWLEDGE | BRIEFING | VAULT | SPACE | CHAT | CLARIFY

CLARIFY = user wants an action but essential info is missing (no hub, no amount, no date)
VAULT = user wants to save something without specifying where
BRIEFING = user asks about their day, week, or status
SPACE = user wants to create or organize spaces/hubs

Return ONLY valid JSON: {{"intents":["TASK"],"primary":"TASK"}}

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


# ── Node 4: Main response (Claude Sonnet 4.6 via OpenRouter) ──────────────────
async def node_respond(state: AgentState) -> AgentState:
    tasks_text = "\n".join([
        f"- {t['title']} ({t['status']}, {t.get('priority','low')}) [id:{t['id']}]"
        for t in state.get("tasks", [])
    ]) or "No active tasks."

    hubs_text = "\n".join([
        f"- {h['name']} — {h.get('space_name','')} [id:{h['id']}]"
        for h in state.get("hubs", [])
    ]) or "No hubs found."

    memory_text = "\n".join([f"- {m['content']}" for m in state.get("memories", [])])
    history_text = "\n".join([
        f"{m['role']}: {m['content'][:200]}" for m in state.get("history", [])[-6:]
    ])

    context = f"""Tasks:
{tasks_text}

Hubs:
{hubs_text}

What you know about this user:
{memory_text or 'Nothing yet.'}

Recent conversation:
{history_text}

User: {state['user_message']}"""

    messages = [SystemMessage(content=AGENT_SYSTEM), HumanMessage(content=context)]
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
