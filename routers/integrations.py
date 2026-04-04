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
    code: str, 
    state: Optional[str] = None, # user_id passed via state
    error: Optional[str] = None
):
    """Handles the Google OAuth callback."""
    if error:
        raise HTTPException(status_code=400, detail=f"Google Auth Error: {error}")
    
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code.")
    
    # state is packed as "user_id:code_verifier"
    print(f"[Google Auth] Callback received state: {state}")
    user_id = state
    code_verifier = None
    if state and ":" in state:
        user_id, code_verifier = state.split(":", 1)
    
    print(f"[Google Auth] Unpacked user_id: {user_id}, code_verifier: {'PRESENT' if code_verifier else 'NONE'}")
    
    # Exchange code for tokens
    google_auth_service.exchange_code(code, user_id, code_verifier)
    
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
