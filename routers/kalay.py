from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import json
from database import supabase
from services.kalay_agent import process_kalay_chat_stream, parse_and_execute_actions

router = APIRouter(prefix="/kalay", tags=["kalay"])

class KalayChatRequest(BaseModel):
    user_id: str
    session_id: Optional[str] = None
    message: str
    space_ids: List[str] = []
    hub_ids: List[str] = []

class KalayOutput(BaseModel):
    type: str # report | presentation | summary | plan
    title: str
    content: str
    space_ids: List[str] = []
    hub_ids: List[str] = []
    session_id: Optional[str] = None

class QuizSubmit(BaseModel):
    user_id: str
    answers: dict # question_id -> answer

# --- Quiz Endpoints ---

@router.get("/quizzes/{quiz_id}")
async def get_quiz(quiz_id: str):
    res = supabase.table("kalay_quizzes").select("*").eq("id", quiz_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    questions = supabase.table("kalay_quiz_questions").select("*").eq("quiz_id", quiz_id).execute()
    return {
        "quiz": res.data,
        "questions": questions.data
    }

@router.post("/quizzes/{quiz_id}/submit")
async def submit_quiz(quiz_id: str, body: QuizSubmit):
    # Fetch questions for scoring
    q_res = supabase.table("kalay_quiz_questions").select("*").eq("quiz_id", quiz_id).execute()
    questions = q_res.data
    
    score = 0
    total = sum(q.get("points", 1) for q in questions)
    
    for q in questions:
        q_id = q["id"]
        user_ans = body.answers.get(q_id)
        correct_ans = q["correct_answer"]
        
        if q["type"] in ["multiple_choice", "boolean"]:
            if str(user_ans).strip().lower() == str(correct_ans).strip().lower():
                score += q.get("points", 1)
        # For essay/paragraph, we might need an AI agent call later to grade semantically.
        # For now, we'll give 0 until manual/AI review.

    res = supabase.table("kalay_quiz_attempts").insert({
        "quiz_id": quiz_id,
        "user_id": body.user_id,
        "answers": body.answers,
        "score": score,
        "total_points": total
    }).execute()
    
    return res.data[0]

# --- Sessions & History ---

@router.get("/sessions/{user_id}")
async def get_sessions(user_id: str):
    res = supabase.table("kalay_sessions") \
        .select("*") \
        .eq("user_id", user_id) \
        .order("updated_at", desc=True) \
        .execute()
    return res.data

@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str):
    res = supabase.table("kalay_messages") \
        .select("*") \
        .eq("session_id", session_id) \
        .order("created_at", desc=False) \
        .execute()
    return res.data

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    supabase.table("kalay_sessions").delete().eq("id", session_id).execute()
    return {"deleted": True}

# --- Core Interaction ---

@router.post("/chat")
async def chat(body: KalayChatRequest, background_tasks: BackgroundTasks):
    # If no session, create one
    session_id = body.session_id
    if not session_id:
        res = supabase.table("kalay_sessions").insert({
            "user_id": body.user_id,
            "title": body.message[:40] + "...",
            "context_space_ids": body.space_ids,
            "context_hub_ids": body.hub_ids,
        }).execute()
        session_id = res.data[0]["id"]
    
    # Save user message
    supabase.table("kalay_messages").insert({
        "session_id": session_id,
        "role": "user",
        "content": body.message,
    }).execute()

    async def stream_generator():
        full_text = ""
        async for chunk in process_kalay_chat_stream(
            user_id=body.user_id,
            session_id=session_id,
            message=body.message,
            space_ids=body.space_ids,
            hub_ids=body.hub_ids
        ):
            full_text += chunk
            yield chunk
        
        # After stream finishes, handle actions and persistence
        # We need to parse actions to send them to the mobile app
        # But how to send them in a stream? I'll use a delimiter
        clean_reply, actions = await parse_and_execute_actions(
            user_id=body.user_id,
            session_id=session_id,
            full_text=full_text,
            space_ids=body.space_ids,
            hub_ids=body.hub_ids
        )

        # Persist assistant message to DB
        supabase.table("kalay_messages").insert({
            "session_id": session_id,
            "role": "assistant",
            "content": clean_reply,
            "actions": actions
        }).execute()

        # Update session timestamp
        supabase.table("kalay_sessions").update({
            "updated_at": "now()"
        }).eq("id", session_id).execute()

        # Yield the final metadata (actions + session_id)
        yield f"|||{json.dumps({'session_id': session_id, 'actions': actions})}"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")

# --- Outputs Repository ---

@router.get("/outputs/{user_id}")
async def get_outputs(user_id: str):
    res = supabase.table("kalay_outputs") \
        .select("*") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .execute()
    return res.data

@router.delete("/outputs/{output_id}")
async def delete_output(output_id: str):
    supabase.table("kalay_outputs").delete().eq("id", output_id).execute()
    return {"deleted": True}

@router.post("/outputs")
async def create_output(user_id: str, body: KalayOutput):
    res = supabase.table("kalay_outputs").insert({
        "user_id": user_id,
        "session_id": body.session_id,
        "type": body.type,
        "title": body.title,
        "content": body.content,
        "space_ids": body.space_ids,
        "hub_ids": body.hub_ids,
    }).execute()
    return res.data[0]
