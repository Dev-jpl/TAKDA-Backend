from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from database import supabase
from services.ai import get_ai_response_async

router = APIRouter(prefix="/aly", tags=["aly"])

# In-memory cache: { user_id: { "date": "YYYY-MM-DD", "insight": "..." } }
_insight_cache: dict[str, dict] = {}

@router.get("/daily-insight")
async def daily_insight(user_id: str):
    try:
        now_utc = datetime.now(timezone.utc)
        now_pht = now_utc + timedelta(hours=8)
        today_str = now_pht.strftime("%A, %B %-d, %Y")
        today_date = now_pht.date().isoformat()

        # Return cached insight if it's still for today
        cached = _insight_cache.get(user_id)
        if cached and cached.get("date") == today_date and cached.get("insight"):
            return {"insight": cached["insight"]}

        # ── Today's calendar events (PHT window = UTC-8h to UTC+16h)
        day_start_utc = (now_pht.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=8)).isoformat()
        day_end_utc   = (now_pht.replace(hour=23, minute=59, second=59, microsecond=0) - timedelta(hours=8)).isoformat()
        events_res = supabase.table("events") \
            .select("title,start_at,end_at,location") \
            .eq("user_id", user_id) \
            .gte("start_at", day_start_utc) \
            .lte("start_at", day_end_utc) \
            .order("start_at") \
            .limit(10).execute()
        events = events_res.data or []

        # ── Active tasks (with titles)
        tasks_res = supabase.table("tasks") \
            .select("title,priority,due_date") \
            .eq("user_id", user_id) \
            .neq("status", "done") \
            .order("due_date") \
            .limit(10).execute()
        tasks = tasks_res.data or []

        # ── Unprocessed vault items
        vault_res = supabase.table("vault_items") \
            .select("id") \
            .eq("user_id", user_id) \
            .eq("status", "unprocessed") \
            .execute()
        vault_count = len(vault_res.data or [])

        # ── Today's expenses — table may not exist yet, skip gracefully
        expenses = []
        total_spent = 0.0
        try:
            expenses_res = supabase.table("expenses") \
                .select("amount,merchant,category") \
                .eq("user_id", user_id) \
                .eq("date", today_date) \
                .execute()
            expenses = expenses_res.data or []
            total_spent = sum(float(e.get("amount", 0)) for e in expenses)
        except Exception:
            pass  # table doesn't exist yet

        # ── Build context
        def fmt_time(iso):
            try:
                dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                pht = dt + timedelta(hours=8)
                return pht.strftime("%-I:%M %p")
            except Exception:
                return iso[:10]

        events_text = "\n".join(
            f"- {e['title']} at {fmt_time(e['start_at'])}" + (f" [{e['location']}]" if e.get("location") else "")
            for e in events
        ) if events else "No events today."

        tasks_text = "\n".join(
            f"- [{t.get('priority','low')}] {t['title']}" + (f" (due {t['due_date']})" if t.get("due_date") else "")
            for t in tasks
        ) if tasks else "No active tasks."

        expenses_text = f"₱{total_spent:.0f} spent today across {len(expenses)} transaction(s)." if expenses else "No spending today."

        context = f"""Today is {today_str} in the Philippines.

Schedule today:
{events_text}

Active tasks:
{tasks_text}

Spending: {expenses_text}
Vault items to sort: {vault_count}"""

        system = (
            "You are Aly, a warm personal assistant. "
            "Write a brief morning briefing (3-6 lines max) for the user's home screen. "
            "Use Markdown: bold key items, use bullet points if helpful. "
            "Be encouraging and specific. Reference actual events and tasks by name. "
            "Do not use headers. Keep it warm and conversational."
        )

        insight = await get_ai_response_async(system, context)
        result  = insight.strip()

        # Store in server-side cache for the rest of the day
        _insight_cache[user_id] = {"date": today_date, "insight": result}

        return {"insight": result}

    except Exception as e:
        print(f"[daily_insight] error for user {user_id}: {e}")
        return {"insight": ""}
