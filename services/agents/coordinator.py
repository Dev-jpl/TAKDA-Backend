from services.ai import get_ai_response_async, get_streaming_ai_response
import json

COORDINATOR_PROMPT = """You are the Kalay Orchestrator. Your role is INTENT CLASSIFICATION and ROUTING.
Analyze the user's message and determine which specialized sub-agent is best suited to handle it.

SUB-AGENTS:
1. CONVERSATION: General chat, greeting, or unclear intent.
2. QUIZ: "Make a quiz...", "Test me on...", "Quiz about [topic]".
3. REPORT: "Generate a report...", "Create a project plan...", "Executive summary".
4. TASK: "Add a task...", "Remember to...", "Todo: ...".
5. SPACE_MANAGEMENT: "Create a space...", "New hub...", "Setup project...".
6. ANNOTATION: "Highlight this...", "Annotate [doc]...", "Link these notes".
7. CALENDAR: "Schedule a meeting...", "Set an event for...", "Add to my calendar".

OUTPUT REQUIREMENT:
Return ONLY the JSON-formatted classification.
{ "intent": "QUIZ", "reason": "...", "confidence": 0.95 }
"""

class AgentCoordinator:
    @staticmethod
    async def classify_intent(message: str) -> dict:
        system_prompt = COORDINATOR_PROMPT
        user_prompt = f"Identify the intent for this message: '{message}'"
        
        response = await get_ai_response_async(system_prompt, user_prompt)
        try:
            # Basic JSON extraction in case the model adds extra text
            import re
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {"intent": "CONVERSATION", "reason": "fallback"}
        except:
            return {"intent": "CONVERSATION", "reason": "error"}

    @staticmethod
    async def route_request(intent: str, **kwargs):
        # This will be used in kalay_agent.py to route the stream
        # I'll implement the actual routing logic directly in kalay_agent.py for now
        # to keep imports clean, but this class serves the classification.
        pass
