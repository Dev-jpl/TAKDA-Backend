from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date, timedelta
import calendar
from database import supabase

router = APIRouter(prefix="/addons", tags=["addons"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class InstallAddonBody(BaseModel):
    hub_id: str
    user_id: str
    type: str
    config: dict = {}

class UpdateAddonConfigBody(BaseModel):
    config: dict

class LogFoodBody(BaseModel):
    user_id: str
    food_name: str
    calories: Optional[float] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    meal_type: str = "meal"
    logged_at: Optional[str] = None

class LogExpenseBody(BaseModel):
    user_id: str
    amount: float
    item: Optional[str] = None
    merchant: Optional[str] = None
    category: str = "General"
    currency: str = "PHP"
    date: Optional[str] = None


# ── Addon CRUD ────────────────────────────────────────────────────────────────

@router.get("/{hub_id}")
async def list_addons(hub_id: str):
    """List all addons installed on a hub."""
    res = supabase.table("hub_addons").select("*").eq("hub_id", hub_id).order("created_at").execute()
    return res.data


@router.post("")
async def install_addon(body: InstallAddonBody):
    """Install an addon on a hub (idempotent — returns existing if already installed)."""
    # Check if already installed
    existing = supabase.table("hub_addons") \
        .select("*").eq("hub_id", body.hub_id).eq("type", body.type).execute()
    if existing.data:
        return existing.data[0]

    res = supabase.table("hub_addons").insert({
        "hub_id": body.hub_id,
        "user_id": body.user_id,
        "type": body.type,
        "config": body.config,
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to install addon")
    return res.data[0]


@router.patch("/{addon_id}/config")
async def update_addon_config(addon_id: str, body: UpdateAddonConfigBody):
    """Update an addon's config (e.g. calorie goal)."""
    supabase.table("hub_addons").update({"config": body.config}).eq("id", addon_id).execute()
    return {"status": "success"}


@router.delete("/{addon_id}")
async def uninstall_addon(addon_id: str):
    """Uninstall an addon from a hub (data is NOT deleted)."""
    supabase.table("hub_addons").delete().eq("id", addon_id).execute()
    return {"status": "success"}


# ── Calorie Counter logs ──────────────────────────────────────────────────────

@router.get("/{hub_id}/calorie_counter/logs")
async def get_calorie_logs(hub_id: str, date: Optional[str] = Query(None), limit: Optional[int] = Query(None)):
    """Get food logs for a hub using module system."""
    # Get module def
    def_res = supabase.table("module_definitions").select("id").eq("slug", "calorie_counter").execute()
    if not def_res.data:
        return []
    def_id = def_res.data[0]["id"]

    q = supabase.table("module_entries").select("*").eq("module_def_id", def_id).eq("hub_id", hub_id)
    
    if date:
        # Simple string prefix match on the ISO string in JSONB
        q = q.filter("data->>logged_at", "like", f"{date}%")
    
    q = q.order("created_at", desc=True)
    if limit:
        q = q.limit(limit)
    res = q.execute()
    
    # Map back to old format for compatibility
    return [{"id": r["id"], **r["data"], "created_at": r["created_at"], "user_id": r["user_id"], "hub_id": r["hub_id"]} for r in res.data]


@router.post("/{hub_id}/calorie_counter/logs")
async def log_food(hub_id: str, body: LogFoodBody):
    """Log a food entry using module system."""
    def_res = supabase.table("module_definitions").select("id").eq("slug", "calorie_counter").execute()
    if not def_res.data:
        raise HTTPException(status_code=404, detail="Module not found")
    def_id = def_res.data[0]["id"]

    data = {
        "food_name": body.food_name,
        "calories": body.calories,
        "protein_g": body.protein_g,
        "carbs_g": body.carbs_g,
        "fat_g": body.fat_g,
        "meal_type": body.meal_type,
        "logged_at": body.logged_at or datetime.now().isoformat(),
    }

    res = supabase.table("module_entries").insert({
        "module_def_id": def_id,
        "hub_id": hub_id,
        "user_id": body.user_id,
        "data": data
    }).execute()
    
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to log food")
    
    r = res.data[0]
    return {"id": r["id"], **r["data"], "created_at": r["created_at"], "user_id": r["user_id"], "hub_id": r["hub_id"]}


@router.delete("/calorie_counter/logs/{log_id}")
async def delete_food_log(log_id: str):
    """Delete a food log entry from module_entries."""
    supabase.table("module_entries").delete().eq("id", log_id).execute()
    return {"status": "success"}


# ── Expense Tracker logs ──────────────────────────────────────────────────────

@router.get("/{hub_id}/expense_tracker/logs")
async def get_expense_logs(hub_id: str, month: Optional[str] = Query(None)):
    """Get expense logs for a hub using module system."""
    def_res = supabase.table("module_definitions").select("id").eq("slug", "expense_tracker").execute()
    if not def_res.data:
        return []
    def_id = def_res.data[0]["id"]

    q = supabase.table("module_entries").select("*").eq("module_def_id", def_id).eq("hub_id", hub_id)
    
    if month:
        q = q.filter("data->>date", "like", f"{month}%")

    res = q.order("created_at", desc=True).execute()
    
    # Map back to old format
    return [{"id": r["id"], **r["data"], "created_at": r["created_at"], "user_id": r["user_id"], "hub_id": r["hub_id"]} for r in res.data]


@router.post("/{hub_id}/expense_tracker/logs")
async def log_expense(hub_id: str, body: LogExpenseBody):
    """Log an expense using module system."""
    def_res = supabase.table("module_definitions").select("id").eq("slug", "expense_tracker").execute()
    if not def_res.data:
        raise HTTPException(status_code=404, detail="Module not found")
    def_id = def_res.data[0]["id"]

    data = {
        "amount": body.amount,
        "item": body.item,
        "merchant": body.merchant,
        "category": body.category,
        "currency": body.currency,
        "date": body.date or datetime.now().date().isoformat(),
    }

    res = supabase.table("module_entries").insert({
        "module_def_id": def_id,
        "hub_id": hub_id,
        "user_id": body.user_id,
        "data": data
    }).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to log expense")
    
    r = res.data[0]
    return {"id": r["id"], **r["data"], "created_at": r["created_at"], "user_id": r["user_id"], "hub_id": r["hub_id"]}


@router.delete("/expense_tracker/logs/{expense_id}")
async def delete_expense(expense_id: str):
    """Delete an expense log from module_entries."""
    supabase.table("module_entries").delete().eq("id", expense_id).execute()
    return {"status": "success"}


# ── Sleep Tracker logs ────────────────────────────────────────────────────────

@router.get("/{hub_id}/sleep_tracker/logs")
async def get_sleep_logs(hub_id: str, limit: Optional[int] = Query(None)):
    """Get sleep logs for a hub. Returns empty list until sleep_logs table is created."""
    return []


# ── Workout Log logs ──────────────────────────────────────────────────────────

@router.get("/{hub_id}/workout_log/logs")
async def get_workout_logs(hub_id: str, limit: Optional[int] = Query(None)):
    """Get workout logs for a hub. Returns empty list until workout_logs table is created."""
    return []
