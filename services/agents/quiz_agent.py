from services.ai import get_streaming_ai_response, get_ai_response, search_chunks
from database import supabase
import json
import re

QUIZ_PROMPT = """You are the Kalay Quiz Agent. Your mission is to transform documents into testing material.
Generate a quiz based on the user's request and the provided context.

QUESTION FORMATS:
1. multiple_choice: { "question": "...", "options": ["A", "B", "C", "D"], "correct_answer": "...", "explanation": "..." }
2. boolean: { "question": "...", "correct_answer": "True/False", "explanation": "..." }
3. short_paragraph: { "question": "...", "correct_answer": "Expected key points", "explanation": "..." }
4. essay: { "question": "...", "correct_answer": "Rubric for grading", "explanation": "..." }

OUTPUT REQUIREMENT:
You must return a list of JSON objects representing the questions.
Surround your final JSON output with [QUIZ_DATA]...[/QUIZ_DATA] markers.
Provide a conversational introduction first, explaining the topic.
"""

async def generate_quiz_stream(user_id: str, topic: str, context_docs: str, types: list[str] = None):
    # Specialized prompt for generating quiz content
    system_prompt = QUIZ_PROMPT
    user_prompt = f"Topic: {topic}\nContext:\n{context_docs}\n\nPlease generate a quiz with {', '.join(types or ['multiple_choice'])}."

    async for chunk in get_streaming_ai_response(system_prompt, user_prompt):
        yield chunk

async def save_quiz_to_db(user_id: str, session_id: str, title: str, topic: str, questions: list):
    # 1. Create Quiz Header
    res = supabase.table("kalay_quizzes").insert({
        "user_id": user_id,
        "session_id": session_id,
        "title": title,
        "topic": topic
    }).execute()
    
    if not res.data:
        return None
    
    quiz_id = res.data[0]["id"]
    
    # 2. Insert Questions
    for q in questions:
        supabase.table("kalay_quiz_questions").insert({
            "quiz_id": quiz_id,
            "type": q.get("type", "multiple_choice"),
            "question": q.get("question", ""),
            "options": q.get("options", []),
            "correct_answer": str(q.get("correct_answer", "")),
            "explanation": q.get("explanation", "")
        }).execute()
        
    return quiz_id
