from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from database import supabase
from services.ai import get_ai_response_async
import json

router = APIRouter(prefix="/automate", tags=["automate"])

class BriefingRequest(BaseModel):
    hub_id: str
    user_id: str
    type: str = "daily" # daily | project

@router.get("/briefings/{hub_id}")
async def get_briefings(hub_id: str):
    """Fetch history of AI briefings for a given hub."""
    res = supabase.table("briefings") \
        .select("*") \
        .eq("hub_id", hub_id) \
        .order("created_at", desc=True) \
        .execute()
    return res.data

@router.post("/briefings/generate")
async def generate_briefing(body: BriefingRequest):
    """
    Synthesize project state across Track, Annotate, and Deliver 
    using AI to generate a 'Royal Briefing'.
    """
    # 1. Fetch Context
    tasks = supabase.table("tasks").select("title, status").eq("hub_id", body.hub_id).execute().data or []
    annos = supabase.table("annotations").select("content, category").eq("hub_id", body.hub_id).execute().data or []
    deliveries = supabase.table("deliveries").select("content, type").eq("hub_id", body.hub_id).execute().data or []

    # 2. Prepare Prompt
    context_str = f"PROJECT STATE FOR HUB {body.hub_id}:\n\n"
    
    context_str += "--- TRACK (TASKS) ---\n"
    for t in tasks:
        context_str += f"- [{t['status'].upper()}] {t['title']}\n"
    
    context_str += "\n--- ANNOTATE (INSIGHTS) ---\n"
    for a in annos:
        context_str += f"- [{a['category'].upper()}] {a['content']}\n"
        
    context_str += "\n--- DELIVER (DISPATCHES) ---\n"
    for d in deliveries:
        context_str += f"- [{d['type'].upper()}] {d['content']}\n"

    system_prompt = """You are TAKDA's Agentic Orchestrator. 
Generate a premium 'Royal Briefing' summarizing the current project state.
Use professional, high-agency language. 
Structure:
1. Executive Summary: High-level status.
2. Mission Velocity: Commentary on tasks.
3. Emerging Insights: Key takeaways from annotations.
4. Recent pivots: Summary of decisions/dispatches.
5. Recommendation: One clear next action.
Be concise. Do not use emojis."""

    user_prompt = f"Synthesize this context into a structured briefing:\n\n{context_str}"

    # 3. Call AI
    try:
        ai_summary = await get_ai_response_async(system_prompt, user_prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI synthesis failed: {str(e)}")

    # 4. Save to Database
    res = supabase.table("briefings").insert({
        "hub_id": body.hub_id,
        "user_id": body.user_id,
        "title": f"{body.type.capitalize()} Rhythm Briefing",
        "content": ai_summary,
        "type": body.type,
    }).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to secure briefing unit.")

    return res.data[0]

@router.delete("/briefings/{briefing_id}")
async def delete_briefing(briefing_id: str):
    """Remove a briefing historical record."""
    supabase.table("briefings") \
        .delete() \
        .eq("id", briefing_id) \
        .execute()
    return {"deleted": True}
