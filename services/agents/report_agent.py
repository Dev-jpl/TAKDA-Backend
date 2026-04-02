from services.ai import get_streaming_ai_response
import json

REPORT_PROMPT = """You are the Kalay Report Agent. Your task is to synthesize disparate data into a professional, structured document.
Support formats like: Project Plan, Executive Summary, Meeting Notes, and Analytical Review.

REPORT REQUIREMENTS:
- Use consistent markdown headers.
- Include an "Executive Summary" at the top.
- End with a "Next Steps" or "Recommendations" section.
- Provide a conversational intro first.
"""

async def generate_report_stream(user_id: str, topic: str, context_docs: str, context_tasks: str, report_type: str = "report"):
    system_prompt = REPORT_PROMPT
    user_prompt = f"Topic: {topic}\nType: {report_type}\n\nContext Tasks:\n{context_tasks}\n\nContext Docs:\n{context_docs}\n\nPlease generate a thorough {report_type}."

    async for chunk in get_streaming_ai_response(system_prompt, user_prompt):
        yield chunk
