from langgraph.graph import StateGraph, END
from services.agent_graph.state import AgentState
from services.agent_graph.nodes import (
    node_load_context,
    node_classify_intent,
    node_check_clarification,
    node_respond,
    node_extract_memories,
)


def route_after_classify(state: AgentState) -> str:
    if state.get("intent") == "CLARIFY":
        return "check_clarification"
    return "respond"


def route_after_clarification(state: AgentState) -> str:
    if state.get("needs_clarification"):
        return "extract_memories"
    return "respond"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("load_context",        node_load_context)
    graph.add_node("classify_intent",     node_classify_intent)
    graph.add_node("check_clarification", node_check_clarification)
    graph.add_node("respond",             node_respond)
    graph.add_node("extract_memories",    node_extract_memories)

    graph.set_entry_point("classify_intent")
    graph.add_edge("classify_intent", "load_context")

    graph.add_conditional_edges("load_context", route_after_classify, {
        "check_clarification": "check_clarification",
        "respond": "respond",
    })

    graph.add_conditional_edges("check_clarification", route_after_clarification, {
        "respond": "respond",
        "extract_memories": "extract_memories",
    })

    graph.add_edge("respond", "extract_memories")
    graph.add_edge("extract_memories", END)

    return graph.compile()


# Compiled once on startup, reused across all requests
agent_graph = build_graph()
