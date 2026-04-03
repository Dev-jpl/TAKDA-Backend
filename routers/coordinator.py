import json
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from database import supabase
from services.coordinator_agent import process_coordinator_chat_stream, parse_and_propose_actions

router = APIRouter()

class CoordinatorChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: Optional[str] = None
    space_ids: List[str] = []
    hub_ids: List[str] = []

@router.get("/sessions/{user_id}")
async def get_sessions(user_id: str):
    res = supabase.table("coordinator_sessions").select("*").eq("user_id", user_id).order("updated_at", desc=True).execute()
    return res.data

@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str):
    res = supabase.table("coordinator_messages").select("*").eq("session_id", session_id).order("created_at", desc=False).execute()
    return res.data

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    supabase.table("coordinator_sessions").delete().eq("id", session_id).execute()
    return {"status": "success"}

@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, body: dict):
    title = body.get("title")
    supabase.table("coordinator_sessions").update({"title": title}).eq("id", session_id).execute()
    return {"status": "success"}

@router.post("/chat")
async def chat(body: CoordinatorChatRequest, background_tasks: BackgroundTasks):
    session_id = body.session_id
    is_new_session = False
    
    if not session_id:
        is_new_session = True
        res = supabase.table("coordinator_sessions").insert({
            "user_id": body.user_id,
            "title": "New Mission"
        }).execute()
        session_id = res.data[0]["id"]

    # Persist user message
    supabase.table("coordinator_messages").insert({
        "session_id": session_id,
        "role": "user",
        "content": body.message
    }).execute()

    # Fetch conversation history for context
    history_res = supabase.table("coordinator_messages") \
        .select("role, content") \
        .eq("session_id", session_id) \
        .order("created_at", desc=True) \
        .limit(11) \
        .execute()
    
    # Reverse to get chronological order, excluding the current message we just added (or keep it if needed)
    # We want the messages BEFORE the current one for history
    raw_history = history_res.data[::-1] if history_res.data else []
    conversation_history = [
        {"role": m["role"], "content": m["content"]}
        for m in raw_history[:-1] # Remove the user message we just inserted to provide it separately
    ]

    # Fetch context for the agent
    tasks_res = supabase.table("tasks").select("id, title, status").eq("user_id", body.user_id).neq("status", "done").execute()
    hubs_res = supabase.table("hubs").select("id, name").eq("user_id", body.user_id).execute()
    context = {
        "tasks": tasks_res.data or [],
        "hubs": hubs_res.data or []
    }

    async def stream_generator():
        full_text = ""
        # 1. AI Response Stream
        async for chunk in process_coordinator_chat_stream(
            user_id=body.user_id,
            message=body.message,
            conversation_history=conversation_history,
            context=context
        ):
            full_text += chunk
            yield chunk
        
        # 2. Finalize actions (Propose NO immediate execute)
        clean_reply, actions = await parse_and_propose_actions(
            user_id=body.user_id,
            session_id=session_id,
            full_text=full_text,
            space_ids=body.space_ids,
            hub_ids=body.hub_ids
        )

        # 3. Persist assistant message to DB
        supabase.table("coordinator_messages").insert({
            "session_id": session_id,
            "role": "assistant",
            "content": clean_reply,
            "actions": actions
        }).execute()

        # Update session timestamp
        supabase.table("coordinator_sessions").update({
            "updated_at": "now()"
        }).eq("id", session_id).execute()

        # Auto-generate title for new sessions
        if is_new_session:
            from services.coordinator_agent import generate_session_title
            # We use a simple history for the title generator
            history = [{"role": "user", "content": body.message}, {"role": "assistant", "content": clean_reply}]
            background_tasks.add_task(async_update_title, session_id, history)

        # Yield metadata
        yield f"|||{json.dumps({'session_id': session_id, 'actions': actions})}"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")

@router.post("/execute_proposal")
async def execute_proposal(body: dict):
    """Executes a previously proposed and confirmed action."""
    user_id = body.get("user_id")
    action_type = body.get("action_type")
    data = body.get("data", {})

    if not user_id or not action_type:
        raise HTTPException(status_code=400, detail="Missing user_id or action_type")

    try:
        if action_type == "CREATE_TASK":
            from services.task_service import execute_task_action
            # Reconstruct the tag for the existing task_service
            tag = f'title="{data.get("title")}" hub_id="{data.get("hub_id")}" priority="{data.get("priority", "low")}"'
            result = await execute_task_action(tag, user_id)
            return {"status": "success", "data": result}
            
        elif action_type == "UPDATE_TASK":
            if data.get("id"):
                updates = {k: v for k, v in data.items() if k != "id"}
                supabase.table("tasks").update(updates).eq("id", data["id"]).execute()
                return {"status": "success", "id": data["id"]}
                
        elif action_type == "CREATE_EVENT":
            from services.calendar_service import create_event
            result = create_event(
                user_id=user_id,
                title=data.get("title", "Mission Event"),
                start_time=data.get("start_time"),
                end_time=data.get("end_time"),
                location=data.get("location")
            )
            return {"status": "success", "data": result}

        elif action_type == "UPDATE_EVENT":
            from services.calendar_service import update_event
            if data.get("id"):
                updates = {k: v for k, v in data.items() if k != "id"}
                result = update_event(data["id"], updates)
                return {"status": "success", "data": result}

        elif action_type == "DELETE_EVENT":
            from services.calendar_service import delete_event
            if data.get("id"):
                delete_event(data["id"])
                return {"status": "success"}

        elif action_type == "SAVE_REPORT":
            # Execute the report save mission
            supabase.table("coordinator_outputs").insert({
                "user_id": user_id,
                "session_id": data.get("session_id"),
                "type": data.get("type", "report"),
                "title": data.get("title", f"Mission Log {datetime.now().strftime('%Y-%m-%d')}"),
                "content": data.get("content", ""),
                "space_ids": data.get("space_ids", []),
                "hub_ids": data.get("hub_ids", [])
            }).execute()
            return {"status": "success"}

        return {"status": "error", "message": f"Unsupported action type: {action_type}"}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"Mission Protocol Error: {str(ve)}")
    except Exception as e:
        print(f"execute_proposal error: {e}")
        raise HTTPException(status_code=500, detail=f"Logical Integrity Failure: {str(e)}")

async def async_update_title(session_id: str, history: list):
    from services.coordinator_agent import generate_session_title
    new_title = await generate_session_title(history)
    supabase.table("coordinator_sessions").update({"title": new_title}).eq("id", session_id).execute()

@router.get("/outputs/{user_id}")
async def get_outputs(user_id: str):
    res = supabase.table("coordinator_outputs").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    return res.data

@router.get("/recommendations/{user_id}")
async def get_recommendations(user_id: str):
    """Fetches history-based recommendations for contextual swapping."""
    try:
        # Get last 10 messages from this user
        messages_res = supabase.table("coordinator_messages") \
            .select("actions") \
            .not_.is_("actions", "null") \
            .execute()
        
        # Simple extraction logic for the swap service
        # ...
        return {"spaces": [], "hubs": []}
    except Exception as e:
        print(f"Recommendations error: {e}")
        return {"spaces": [], "hubs": []}
