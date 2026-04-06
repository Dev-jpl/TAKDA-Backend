import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from services.strava_auth_service import strava_auth_service
from services.strava_service import strava_service
from typing import Optional

router = APIRouter(prefix="/integrations/strava", tags=["strava"])


@router.get("/auth")
async def strava_auth(user_id: str):
    """Initiates the Strava OAuth flow."""
    auth_url, _ = strava_auth_service.get_auth_url(user_id)
    return {"url": auth_url}


@router.get("/callback")
async def strava_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    scope: Optional[str] = None,
):
    """Handles the Strava OAuth callback."""
    if error:
        raise HTTPException(status_code=400, detail=f"Strava auth error: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code.")

    if not state:
        raise HTTPException(status_code=400, detail="Missing OAuth state.")

    from database import supabase
    try:
        state_result = supabase.table("oauth_states").select("*").eq("id", state).execute()
    except Exception as e:
        if "invalid input syntax for type uuid" in str(e).lower():
            raise HTTPException(status_code=400, detail="Invalid session ID. Please restart the Strava connection flow.")
        raise e

    if not state_result.data:
        raise HTTPException(status_code=400, detail="Invalid or expired session. Please try connecting again.")

    user_id = state_result.data[0]["user_id"]

    # Clean up state record
    supabase.table("oauth_states").delete().eq("id", state).execute()

    # Exchange code for tokens
    strava_auth_service.exchange_code(code, user_id)

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return RedirectResponse(url=f"{frontend_url}/integrations?integration=strava&status=success")


@router.post("/sync")
async def sync_strava(user_id: str, per_page: int = 50):
    """Syncs recent Strava activities into TAKDA."""
    try:
        synced_ids = strava_service.sync_activities(user_id, per_page=per_page)
        return {"status": "success", "synced_count": len(synced_ids)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/activities")
async def get_activities(user_id: str, limit: int = 20, sport_type: Optional[str] = None):
    """Returns synced Strava activities for a user."""
    try:
        activities = strava_service.get_activities(user_id, limit=limit, sport_type=sport_type)
        return {"status": "success", "activities": activities}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile")
async def get_strava_profile(user_id: str):
    """Returns the stored Strava athlete profile."""
    profile = strava_service.get_athlete_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="No Strava integration found.")
    return {"status": "success", "profile": profile}
