import os
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from services.google_auth_service import google_auth_service
from services.google_calendar_service import google_calendar_service
from typing import Optional

router = APIRouter(prefix="/integrations", tags=["integrations"])

@router.get("/google/auth")
async def google_auth(user_id: str):
    """Initiates the Google OAuth flow."""
    auth_url, _ = google_auth_service.get_auth_url(user_id)
    return {"url": auth_url}

@router.get("/google/callback")
async def google_callback(
    code: Optional[str] = None, 
    state: Optional[str] = None, 
    error: Optional[str] = None
):
    """Handles the Google OAuth callback."""
    if error:
        raise HTTPException(status_code=400, detail=f"Google Auth Error: {error}")
    
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code.")
    
    # state is the UUID id from our oauth_states table
    print(f"[Google Auth] Callback received state ID: {state}")
    
    if not state:
        raise HTTPException(status_code=400, detail="Missing OAuth state.")
        
    # Safety check: if state has a colon, it's the OLD format and will cause a UUID crash
    if ":" in state:
        raise HTTPException(
            status_code=400, 
            detail="You are using an outdated authorization session. Please refresh the Settings page and try adding Google Calendar again."
        )
    
    from database import supabase
    try:
        state_result = supabase.table("oauth_states").select("*").eq("id", state).execute()
    except Exception as e:
        # Catch UUID syntax errors from Postgres
        if "invalid input syntax for type uuid" in str(e).lower():
            raise HTTPException(
                status_code=400, 
                detail="Invalid session ID. Please restart the Google connection flow."
            )
        raise e
    
    if not state_result.data:
        raise HTTPException(status_code=400, detail="Invalid OAuth state or session expired. Please try connecting again.")
    
    state_data = state_result.data[0]
    user_id = state_data["user_id"]
    code_verifier = state_data["code_verifier"]
    
    print(f"[Google Auth] Recovered user_id: {user_id} and code_verifier from DB")
    
    # Exchange code for tokens
    google_auth_service.exchange_code(code, user_id, code_verifier)
    
    # Cleanup state
    supabase.table("oauth_states").delete().eq("id", state).execute()
    
    # After successful exchange, redirect back to the frontend settings page
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return RedirectResponse(url=f"{frontend_url}/settings?integration=google&status=success")

@router.post("/google/sync")
async def sync_google_calendar(user_id: str):
    """Manually triggers a sync of Google Calendar events."""
    try:
        synced_ids = google_calendar_service.sync_events(user_id)
        return {"status": "success", "synced_count": len(synced_ids)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/gmail/recent")
async def get_recent_emails(user_id: str, max_results: int = 10):
    """Fetches recent emails for the user."""
    from services.google_gmail_service import google_gmail_service
    try:
        emails = google_gmail_service.get_recent_emails(user_id, max_results)
        return {"status": "success", "emails": emails}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
