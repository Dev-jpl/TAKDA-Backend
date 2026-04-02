from services.ai import get_streaming_ai_response

REPORT_PROMPT = """You are Kalay's report agent inside TAKDA.

Generate clean, structured markdown reports.

Format rules:
- Start with a 2-sentence executive summary
- Use ## headers for sections
- Use bullet points for lists
- End with ## Next steps section
- Keep it dense and useful, not padded

After the report, output EXACTLY this tag on its own line:
[SAVE_REPORT: title="..." type="report|summary|plan|presentation"]
"""

async def run_report_agent_stream(message: str, tasks_context: str, docs_context: str, conversation_history: list = []):
    history_text = "\n".join([
        f"{m['role']}: {m['content'][:150]}"
        for m in (conversation_history[-4:] if conversation_history else [])
    ])

    user_prompt = f"""Recent conversation:
{history_text}

Available tasks data:
{tasks_context or 'No tasks data.'}

Available knowledge:
{docs_context or 'No documents found.'}

User request: "{message}"

Generate the report now."""

    async for chunk in get_streaming_ai_response(REPORT_PROMPT, user_prompt):
        yield chunk