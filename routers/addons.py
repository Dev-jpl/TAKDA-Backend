from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
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


# ── Calorie Counter endpoints ─────────────────────────────────────────────────

@router.get("/{hub_id}/calorie_counter/logs")
async def get_food_logs(hub_id: str, date: Optional[str] = None):
    """Get food logs for this hub, optionally filtered by date (YYYY-MM-DD)."""
    query = supabase.table("food_logs").select("*").eq("hub_id", hub_id)
    if date:
        # Filter to the given day in logged_at
        start = f"{date}T00:00:00"
        end = f"{date}T23:59:59"
        query = query.gte("logged_at", start).lte("logged_at", end)
    res = query.order("logged_at", desc=True).execute()
    return res.data


@router.post("/{hub_id}/calorie_counter/logs")
async def log_food(hub_id: str, body: LogFoodBody):
    """Manually log a food entry for this hub."""
    row = {
        "user_id": body.user_id,
        "hub_id": hub_id,
        "food_name": body.food_name,
        "meal_type": body.meal_type,
        "logged_at": body.logged_at or datetime.now().isoformat(),
    }
    if body.calories is not None:
        row["calories"] = body.calories
    if body.protein_g is not None:
        row["protein_g"] = body.protein_g
    if body.carbs_g is not None:
        row["carbs_g"] = body.carbs_g
    if body.fat_g is not None:
        row["fat_g"] = body.fat_g

    res = supabase.table("food_logs").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to log food")
    return res.data[0]


@router.delete("/calorie_counter/logs/{log_id}")
async def delete_food_log(log_id: str):
    supabase.table("food_logs").delete().eq("id", log_id).execute()
    return {"status": "success"}


# ── Expense Tracker endpoints ─────────────────────────────────────────────────

@router.get("/{hub_id}/expense_tracker/logs")
async def get_expenses(hub_id: str, month: Optional[str] = None):
    """Get expenses for this hub, optionally filtered by month (YYYY-MM)."""
    query = supabase.table("expenses").select("*").eq("hub_id", hub_id)
    if month:
        start = f"{month}-01"
        # Compute end of month
        year, mon = int(month.split("-")[0]), int(month.split("-")[1])
        next_mon = mon + 1 if mon < 12 else 1
        next_year = year if mon < 12 else year + 1
        end = f"{next_year}-{next_mon:02d}-01"
        query = query.gte("date", start).lt("date", end)
    res = query.order("date", desc=True).execute()
    return res.data


@router.post("/{hub_id}/expense_tracker/logs")
async def log_expense(hub_id: str, body: LogExpenseBody):
    """Manually log an expense for this hub."""
    row = {
        "user_id": body.user_id,
        "hub_id": hub_id,
        "amount": body.amount,
        "category": body.category,
        "currency": body.currency,
        "date": body.date or datetime.now().date().isoformat(),
    }
    if body.item:
        row["item"] = body.item
    if body.merchant:
        row["merchant"] = body.merchant

    res = supabase.table("expenses").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to log expense")
    return res.data[0]


@router.delete("/expense_tracker/logs/{expense_id}")
async def delete_expense(expense_id: str):
    supabase.table("expenses").delete().eq("id", expense_id).execute()
    return {"status": "success"}
