from fastapi import APIRouter, HTTPException, Query
from database import supabase
from typing import List, Optional
from pydantic import BaseModel
from datetime import date, datetime, timezone

router = APIRouter(prefix="/fitness", tags=["fitness"])

class FitnessDataPoint(BaseModel):
    date: date
    steps: Optional[int] = 0
    calories_burned: Optional[float] = 0
    distance_meters: Optional[float] = 0
    avg_heart_rate: Optional[float] = None
    metadata: Optional[dict] = {}

class FitnessSyncRequest(BaseModel):
    user_id: str
    data: List[FitnessDataPoint]

@router.post("/sync")
async def sync_fitness_data(payload: FitnessSyncRequest):
    """
    Syncs fitness data points from the mobile app.
    Uses an upsert approach to update existing dates or insert new ones.
    """
    if not payload.data:
        return {"status": "success", "message": "No data to sync"}

    try:
        # Prepare data for Supabase upsert
        upsert_data = []
        for point in payload.data:
            upsert_data.append({
                "user_id": payload.user_id,
                "date": point.date.isoformat(),
                "steps": point.steps,
                "calories_burned": point.calories_burned,
                "distance_meters": point.distance_meters,
                "avg_heart_rate": point.avg_heart_rate,
                "metadata": point.metadata,
                "updated_at": datetime.now(timezone.utc).isoformat()
            })

        # Perform upsert
        result = supabase.table("user_fitness_data").upsert(
            upsert_data, on_conflict="user_id, date"
        ).execute()

        return {
            "status": "success",
            "synced_count": len(upsert_data)
        }
    except Exception as e:
        print(f"[Fitness] Sync error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to sync fitness data: {str(e)}")

@router.get("/summary")
async def get_fitness_summary(
    user_id: str,
    days: int = Query(7, description="Number of past days to retrieve")
):
    """
    Returns fitness summaries for the last N days.
    """
    try:
        result = supabase.table("user_fitness_data") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("date", desc=True) \
            .limit(days) \
            .execute()

        return {
            "status": "success",
            "data": result.data
        }
    except Exception as e:
        print(f"[Fitness] Fetch error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch fitness summary: {str(e)}")
