from datetime import date
from fastapi import APIRouter
from database import supabase
from services.ai import get_ai_response_async

router = APIRouter(prefix="/aly", tags=["aly"])

@router.get("/daily-insight")
async def daily_insight(user_id: str):
    try:
        today = date.today().isoformat()

        # Tasks due today
        tasks_res = supabase.table("tasks") \
            .select("id") \
            .eq("user_id", user_id) \
            .neq("status", "done") \
            .lte("due_date", today) \
            .execute()
        task_count = len(tasks_res.data or [])

        # Unprocessed vault items
        vault_res = supabase.table("vault_items") \
            .select("id") \
            .eq("user_id", user_id) \
            .eq("status", "unprocessed") \
            .execute()
        vault_count = len(vault_res.data or [])

        # Today's expenses total
        expenses_res = supabase.table("expenses") \
            .select("amount") \
            .eq("user_id", user_id) \
            .eq("date", today) \
            .execute()
        total_spent = sum(float(e.get("amount", 0)) for e in (expenses_res.data or []))

        context = f"Tasks due today: {task_count}\nVault items to sort: {vault_count}\nSpent today: ₱{total_spent:.0f}"

        prompt = (
            "Write one warm, specific sentence (max 15 words) summarizing this person's day. "
            "Be encouraging, not alarming. No filler words."
        )

        insight = await get_ai_response_async(prompt, context)
        return {"insight": insight.strip()}

    except Exception as e:
        return {"insight": ""}
