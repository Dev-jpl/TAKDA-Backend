import os
import datetime
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from database import supabase
from typing import Optional, Dict, Any

# Scopes required for Google Calendar
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/gmail.readonly'
]

# Redirect URI (should match what's in Google Console)
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/integrations/google/callback")

class GoogleAuthService:
    @staticmethod
    def get_flow():
        """Creates a Flow object for OAuth."""
        client_config = {
            "web": {
                "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
                "project_id": os.getenv("GOOGLE_PROJECT_ID", "takda-492300"),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
            }
        }
        return Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )

    @staticmethod
    def get_auth_url(user_id: str):
        """Generates the Google OAuth authorization URL, including user_id in the state."""
        flow = GoogleAuthService.get_flow()
        # Generate authorization URL. We call it once to trigger PKCE generation if enabled.
        # We use a placeholder for state and then replace it with our packed state.
        authorization_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state='STATE_PLACEHOLDER'
        )
        
        # Now that flow.code_verifier is populated (if PKCE is used), we pack it.
        verifier = getattr(flow, 'code_verifier', None)
        state = f"{user_id}:{verifier}" if verifier else user_id
        
        # URL-encode the state for safe transmission
        import urllib.parse
        encoded_state = urllib.parse.quote(state)
        
        # Replace the placeholder in the URL
        authorization_url = authorization_url.replace('state=STATE_PLACEHOLDER', f'state={encoded_state}')
        
        print(f"[Google Auth] Generated auth URL with state: {state}")
        return authorization_url, state

    @staticmethod
    def exchange_code(code: str, user_id: str, code_verifier: str = None):
        """Exchanges authorization code for tokens and stores them in Supabase."""
        print(f"[Google Auth] Exchanging code for user: {user_id} with verifier: {'PRESENT' if code_verifier else 'NONE'}")
        flow = GoogleAuthService.get_flow()
        flow.fetch_token(code=code, code_verifier=code_verifier)
        credentials = flow.credentials

        # Store tokens in Supabase
        integration_data = {
            "user_id": user_id,
            "provider": "google",
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "expires_at": credentials.expiry.isoformat() if credentials.expiry else None,
            "scopes": credentials.scopes,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

        # Upsert integration data
        res = supabase.table("user_integrations").upsert(
            integration_data, on_conflict="user_id,provider"
        ).execute()
        
        return res.data[0] if res.data else None

    @staticmethod
    def get_credentials(user_id: str) -> Optional[Credentials]:
        """Retrieves and refreshes Google credentials for a user."""
        res = supabase.table("user_integrations") \
            .select("*") \
            .eq("user_id", user_id) \
            .eq("provider", "google") \
            .execute()
        
        if not res.data:
            return None
        
        data = res.data[0]
        creds = Credentials(
            token=data['access_token'],
            refresh_token=data['refresh_token'],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
            scopes=data['scopes']
        )

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Update tokens in Supabase
            supabase.table("user_integrations").update({
                "access_token": creds.token,
                "expires_at": creds.expiry.isoformat() if creds.expiry else None,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }).eq("user_id", user_id).eq("provider", "google").execute()
            
        return creds

google_auth_service = GoogleAuthService()
