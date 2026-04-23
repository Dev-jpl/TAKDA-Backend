from typing import TypedDict, List


class AgentState(TypedDict):
    # Input
    user_message: str
    user_id: str
    session_id: str
    space_ids: List[str]
    hub_ids: List[str]

    # Context (loaded by node_load_context)
    context_bio: str
    wellbeing_signals: List[str]
    tasks: List[dict]
    hubs: List[dict]
    spaces: List[dict]
    memories: List[dict]
    events: List[dict]
    annotations: List[dict]
    knowledge_docs: List[dict]
    strava_activities: List[dict]
    integrations: List[dict]
    module_definitions: List[dict]
    docs_text: str

    # Conversation history
    history: List[dict]  # [{role, content}]

    # Intent classification
    intent: str
    intents: List[str]

    # Clarification flow
    needs_clarification: bool
    clarification_question: str

    # Output
    response: str
    actions: List[dict]
    tool_results: List[dict]
