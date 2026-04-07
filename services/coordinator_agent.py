import json
from typing import AsyncGenerator
from services.agent_graph.graph import agent_graph
from services.agent_graph.state import AgentState


async def process_coordinator_chat_stream(
    user_id: str,
    message: str,
    conversation_history: list = [],
    context: dict = {},
    session_id: str = "",
    space_ids: list = [],
    hub_ids: list = [],
) -> AsyncGenerator[str, None]:
    """
    LangGraph-based agent pipeline.
    Uses astream_events for real token streaming.
    """
    initial_state: AgentState = {
        "user_message": message,
        "user_id": user_id,
        "session_id": session_id,
        "space_ids": space_ids,
        "hub_ids": hub_ids,
        "history": conversation_history,
        # Pre-load fields — node_load_context will replace these with real data
        "tasks": [],
        "hubs": [],
        "spaces": [],
        "memories": [],
        "events": [],
        "annotations": [],
        "knowledge_docs": [],
        "strava_activities": [],
        "integrations": [],
        "docs_text": "",
        "intent": "",
        "intents": [],
        "needs_clarification": False,
        "clarification_question": "",
        "response": "",
        "actions": [],
        "tool_results": [],
    }

    try:
        actions = []
        async for event in agent_graph.astream_events(initial_state, version="v2"):
            kind = event.get("event", "")

            # Stream text tokens from the main respond node
            if (kind == "on_chat_model_stream" and
                    event.get("metadata", {}).get("langgraph_node") == "respond"):
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield chunk.content

            # Capture final state when graph ends
            elif kind == "on_chain_end" and event.get("name") == "LangGraph":
                final = event.get("data", {}).get("output", {})
                actions = final.get("actions", [])
                # If clarification was needed, yield the question (not streamed above)
                if final.get("needs_clarification"):
                    yield final.get("clarification_question", "")

        # Yield actions metadata at end using delimiter the router expects
        if actions:
            yield f"|||{json.dumps({'actions': actions})}"

    except Exception as e:
        print(f"[process_coordinator_chat_stream] error: {e}")
        yield "Something went wrong. Please try again."


async def parse_and_propose_actions(
    user_id: str,
    session_id: str,
    full_text: str,
    space_ids: list = [],
    hub_ids: list = [],
) -> tuple[str, list]:
    """
    Backward-compatible — router still calls this.
    Splits the ||| metadata delimiter appended by the stream function.
    """
    if "|||" in full_text:
        parts = full_text.split("|||")
        clean_text = parts[0].strip()
        try:
            metadata = json.loads(parts[1])
            actions = metadata.get("actions", [])
        except Exception:
            actions = []
        return clean_text, actions
    return full_text.strip(), []


async def generate_session_title(conversation_history: list) -> str:
    history_snippet = "\n".join([
        f"{m['role']}: {m['content'][:100]}" for m in conversation_history[-3:]
    ])
    from config import ASSISTANT_NAME
    from services.ai import get_ai_response_async
    system = f"You are {ASSISTANT_NAME}'s summarizer. Create a 3-5 word title for this chat. No quotes, no filler."
    title = await get_ai_response_async(system, history_snippet)
    return title.strip().replace('"', '')
