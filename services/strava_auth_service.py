import os
import datetime
import httpx
import urllib.parse
from database import supabase
from typing import Optional, Dict, Any

STRAVA_CLIENT_ID = int(os.getenv("STRAVA_CLIENT_ID", "0"))
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
STRAVA_REDIRECT_URI = os.getenv(
    "STRAVA_REDIRECT_URI",
    "http://localhost:8000/integrations/strava/callback"
)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_SCOPE = "activity:read_all,profile:read_all"


class StravaAuthService:

    @staticmethod
    def get_auth_url(user_id: str) -> tuple[str, str]:
        """Generates the Strava OAuth authorization URL and stores state in DB."""
        # Store a state record (no PKCE for Strava, code_verifier is empty string)
        result = supabase.table("oauth_states").insert({
            "user_id": user_id,
            "code_verifier": ""  # Strava doesn't use PKCE
        }).execute()

        state_id = result.data[0]["id"]
        print(f"[Strava Auth] Generated state ID: {state_id}")

        params = {
            "client_id": STRAVA_CLIENT_ID,
            "redirect_uri": STRAVA_REDIRECT_URI,
            "response_type": "code",
            "approval_prompt": "auto",
            "scope": STRAVA_SCOPE,
            "state": state_id,
        }
        auth_url = STRAVA_AUTH_URL + "?" + urllib.parse.urlencode(params)
        return auth_url, state_id

    @staticmethod
    def exchange_code(code: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Exchanges authorization code for tokens and stores them in Supabase."""
        print(f"[Strava Auth] Exchanging code for user: {user_id}")
        with httpx.Client() as client:
            res = client.post(STRAVA_TOKEN_URL, files={
                "client_id":     (None, str(STRAVA_CLIENT_ID)),
                "client_secret": (None, STRAVA_CLIENT_SECRET),
                "code":          (None, code),
                "grant_type":    (None, "authorization_code"),
            })
            print(f"[Strava] Token exchange status: {res.status_code}")
            print(f"[Strava] Token exchange response: {res.text}")
            res.raise_for_status()
            token_data = res.json()

        athlete = token_data.get("athlete", {})
        expires_at = datetime.datetime.fromtimestamp(
            token_data["expires_at"], tz=datetime.timezone.utc
        )

        integration_data = {
            "user_id": user_id,
            "provider": "strava",
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
            "expires_at": expires_at.isoformat(),
            "scopes": token_data.get("scope", STRAVA_SCOPE).split(","),
            "metadata": {
                "athlete_id": athlete.get("id"),
                "firstname": athlete.get("firstname"),
                "lastname": athlete.get("lastname"),
                "username": athlete.get("username"),
                "profile": athlete.get("profile"),  # profile picture URL
            },
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        result = supabase.table("user_integrations").upsert(
            integration_data, on_conflict="user_id,provider"
        ).execute()

        return result.data[0] if result.data else None

    @staticmethod
    def refresh_token(user_id: str) -> Optional[str]:
        """Refreshes the Strava access token and updates Supabase."""
        res = supabase.table("user_integrations") \
            .select("*") \
            .eq("user_id", user_id) \
            .eq("provider", "strava") \
            .execute()

        if not res.data:
            return None

        data = res.data[0]
        with httpx.Client() as client:
            token_res = client.post(STRAVA_TOKEN_URL, files={
                "client_id":     (None, str(STRAVA_CLIENT_ID)),
                "client_secret": (None, STRAVA_CLIENT_SECRET),
                "grant_type":    (None, "refresh_token"),
                "refresh_token": (None, data["refresh_token"]),
            })
            token_res.raise_for_status()
            token_data = token_res.json()

        expires_at = datetime.datetime.fromtimestamp(
            token_data["expires_at"], tz=datetime.timezone.utc
        )
        supabase.table("user_integrations").update({
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", data["refresh_token"]),
            "expires_at": expires_at.isoformat(),
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }).eq("user_id", user_id).eq("provider", "strava").execute()

        return token_data["access_token"]

    @staticmethod
    def get_access_token(user_id: str) -> Optional[str]:
        """Returns a valid access token, refreshing if expired."""
        res = supabase.table("user_integrations") \
            .select("access_token, expires_at") \
            .eq("user_id", user_id) \
            .eq("provider", "strava") \
            .execute()

        if not res.data:
            return None

        data = res.data[0]
        now = datetime.datetime.now(datetime.timezone.utc)

        if data.get("expires_at"):
            expires = datetime.datetime.fromisoformat(data["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=datetime.timezone.utc)
            if expires <= now:
                return StravaAuthService.refresh_token(user_id)

        return data["access_token"]


strava_auth_service = StravaAuthService()
