import httpx
import datetime
from database import supabase
from services.strava_auth_service import strava_auth_service
from typing import List, Dict, Any, Optional

STRAVA_API_BASE = "https://www.strava.com/api/v3"


class StravaService:

    def sync_activities(self, user_id: str, per_page: int = 50) -> List[str]:
        """
        Fetches recent activities from Strava and upserts into strava_activities.
        Returns list of synced Strava activity IDs.
        """
        token = strava_auth_service.get_access_token(user_id)
        if not token:
            raise ValueError("No Strava integration found for this user.")

        headers = {"Authorization": f"Bearer {token}"}
        with httpx.Client() as client:
            res = client.get(
                f"{STRAVA_API_BASE}/athlete/activities",
                headers=headers,
                params={"per_page": per_page},
            )
            res.raise_for_status()
            activities = res.json()

        synced_ids = []
        for activity in activities:
            row = {
                "user_id": user_id,
                "strava_id": str(activity["id"]),
                "name": activity.get("name"),
                "sport_type": activity.get("sport_type") or activity.get("type"),
                "start_date": activity.get("start_date"),
                "distance_meters": activity.get("distance"),
                "moving_time_seconds": activity.get("moving_time"),
                "elapsed_time_seconds": activity.get("elapsed_time"),
                "total_elevation_gain": activity.get("total_elevation_gain"),
                "average_speed": activity.get("average_speed"),
                "max_speed": activity.get("max_speed"),
                "average_heartrate": activity.get("average_heartrate"),
                "max_heartrate": activity.get("max_heartrate"),
                "kudos_count": activity.get("kudos_count", 0),
                "map_summary_polyline": (activity.get("map") or {}).get("summary_polyline"),
            }
            supabase.table("strava_activities").upsert(
                row, on_conflict="user_id,strava_id"
            ).execute()
            synced_ids.append(str(activity["id"]))

        print(f"[Strava] Synced {len(synced_ids)} activities for user {user_id}")
        return synced_ids

    def get_activities(
        self, user_id: str, limit: int = 20, sport_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Returns synced activities from Supabase (no live API call)."""
        query = supabase.table("strava_activities") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("start_date", desc=True) \
            .limit(limit)

        if sport_type:
            query = query.eq("sport_type", sport_type)

        res = query.execute()
        return res.data or []

    def get_athlete_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Returns the Strava athlete profile stored in integration metadata."""
        res = supabase.table("user_integrations") \
            .select("metadata") \
            .eq("user_id", user_id) \
            .eq("provider", "strava") \
            .execute()

        if not res.data:
            return None
        return res.data[0].get("metadata")


strava_service = StravaService()
