from langchain_core.tools import tool
from database import supabase
from datetime import datetime, timedelta


@tool
def create_task(title: str, hub_name: str,
                priority: str = "low",
                due_date: str = None,
                user_id: str = "") -> dict:
    """
    Creates a task in a hub.
    Call when user wants to add, create, or remember a task.
    hub_name: the name of the hub exactly as shown in context (e.g. "Morning Routine")
    priority: low | high | urgent
    due_date: optional ISO date string e.g. 2026-04-25
    """
    # Resolve hub name → id
    res = supabase.table("hubs").select("id,name").eq("user_id", user_id).execute()
    hubs = res.data or []
    hub = next((h for h in hubs if h["name"].lower() == hub_name.lower()), None)
    if not hub:
        # fuzzy fallback: partial match
        hub = next((h for h in hubs if hub_name.lower() in h["name"].lower()), None)
    if not hub:
        return {"success": False, "error": f"Hub '{hub_name}' not found. Available: {[h['name'] for h in hubs]}"}

    row = {
        "title": title, "hub_id": hub["id"],
        "priority": priority, "status": "todo", "user_id": user_id,
    }
    if due_date:
        row["due_date"] = due_date

    result = supabase.table("tasks").insert(row).execute()
    if result.data:
        return {"success": True, "type": "task_created",
                "label": title, "id": result.data[0]["id"],
                "hub": hub["name"]}
    return {"success": False, "error": "Failed to create task"}


@tool
def update_task(task_id: str, status: str = None,
                title: str = None, priority: str = None,
                due_date: str = None) -> dict:
    """
    Updates an existing task.
    status: todo | in_progress | done
    due_date: ISO date string e.g. 2026-04-25, or null to clear
    """
    updates = {k: v for k, v in {
        "status": status, "title": title,
        "priority": priority, "due_date": due_date,
    }.items() if v is not None}
    if not updates:
        return {"success": False, "error": "No fields to update"}
    supabase.table("tasks").update(updates).eq("id", task_id).execute()
    return {"success": True, "type": "task_updated", "id": task_id, **updates}


@tool
def create_event(title: str, start_time: str,
                 end_time: str = None, location: str = None,
                 user_id: str = "") -> dict:
    """
    Creates a calendar event.
    start_time must be ISO 8601 e.g. 2026-04-10T09:00:00
    end_time defaults to 1 hour after start if not given.
    """
    if not end_time:
        dt = datetime.fromisoformat(start_time)
        end_time = (dt + timedelta(hours=1)).isoformat()
    result = supabase.table("events").insert({
        "title": title, "start_at": start_time,
        "end_at": end_time, "location": location, "user_id": user_id,
    }).execute()
    if result.data:
        return {"success": True, "type": "event_created",
                "label": title, "start": start_time}
    return {"success": False, "error": "Failed to create event"}


@tool
def log_expense(amount: float, merchant: str = None,
                category: str = "General", hub_name: str = None,
                user_id: str = "", currency: str = "PHP") -> dict:
    """
    Logs a financial expense (money spent / cost paid).
    ALWAYS prefer this over log_food when:
      - the user explicitly mentions "expense tracker", "spending", "cost", or "budget"
      - the numbers in the message represent PRICES or CURRENCY AMOUNTS (e.g. "rice - 15", "chicken - 79")
      - the user says they "bought", "paid for", or "spent" something
    If the user lists multiple items with prices, call this tool ONCE PER ITEM.
    Do NOT use this for calorie or nutrition tracking — use log_food for that.
    category: General | Food | Transport | Health | Entertainment | Shopping | Utilities | Other
    hub_name: optional hub name to associate the expense with.
    """
    hub_id = None
    if hub_name:
        res = supabase.table("hubs").select("id,name").eq("user_id", user_id).execute()
        hub = next((h for h in (res.data or []) if h["name"].lower() == hub_name.lower()), None)
        if hub:
            hub_id = hub["id"]

    supabase.table("expenses").insert({
        "amount": amount, "merchant": merchant, "category": category,
        "hub_id": hub_id, "user_id": user_id, "currency": currency,
        "date": datetime.now().date().isoformat(),
    }).execute()
    return {"success": True, "type": "expense_logged",
            "label": f"{currency} {amount:.2f} at {merchant or 'unknown'}"}


@tool
def log_food(food_name: str, calories: float = None,
             meal_type: str = "meal", hub_name: str = None,
             user_id: str = "") -> dict:
    """
    Logs a food entry for CALORIE or NUTRITION tracking only.
    ONLY use this when the user is tracking what they ATE (calories, macros, meals) — NOT what they spent.
    Do NOT use this if the user mentions "expense tracker", prices, costs, or currency amounts.
    If the numbers alongside food items represent PRICES (not calories), use log_expense instead.
    meal_type: breakfast | lunch | dinner | snack | meal
    hub_name: optional hub name to associate the entry with.
    """
    hub_id = None
    if hub_name:
        res = supabase.table("hubs").select("id,name").eq("user_id", user_id).execute()
        hub = next((h for h in (res.data or []) if h["name"].lower() == hub_name.lower()), None)
        if hub:
            hub_id = hub["id"]

    supabase.table("food_logs").insert({
        "food_name": food_name, "calories": calories,
        "meal_type": meal_type, "hub_id": hub_id,
        "user_id": user_id, "logged_at": datetime.now().isoformat(),
    }).execute()
    return {"success": True, "type": "food_logged",
            "label": f"{food_name}" + (f" · {calories} kcal" if calories else "")}


@tool
def save_to_vault(content: str, content_type: str = "text",
                  user_id: str = "") -> dict:
    """
    Saves anything to the vault for later sorting.
    Call when user wants to save something without specifying where.
    content_type: text | link | task | note
    """
    supabase.table("vault_items").insert({
        "content": content, "content_type": content_type,
        "user_id": user_id, "status": "unprocessed",
    }).execute()
    return {"success": True, "type": "vault_saved",
            "label": content[:60] + ("..." if len(content) > 60 else "")}


@tool
def save_report(title: str, content: str,
                report_type: str = "report",
                user_id: str = "") -> dict:
    """
    Saves a generated report or summary to outputs.
    report_type: report | summary | plan | briefing
    """
    supabase.table("coordinator_outputs").insert({
        "title": title, "content": content, "type": report_type,
        "user_id": user_id,
    }).execute()
    return {"success": True, "type": "report_saved", "label": title}


@tool
def create_space(name: str, icon: str = "Folder",
                 color: str = "#7F77DD",
                 user_id: str = "") -> dict:
    """
    Creates a new space (life domain) for the user.
    Call when user wants to organize a new area of their life.
    """
    result = supabase.table("spaces").insert({
        "name": name, "icon": icon, "color": color, "user_id": user_id,
    }).execute()
    if result.data:
        return {"success": True, "type": "space_created",
                "label": name, "id": result.data[0]["id"]}
    return {"success": False, "error": "Failed to create space"}


@tool
def create_hub(name: str, space_name: str,
               icon: str = "Folder", color: str = "#7F77DD",
               user_id: str = "") -> dict:
    """
    Creates a new hub inside a space.
    Call when user wants to add a hub/project to an existing space.
    space_name: the name of the space exactly as shown in context (e.g. "Health")
    """
    # Resolve space name → id
    res = supabase.table("spaces").select("id,name").eq("user_id", user_id).execute()
    spaces = res.data or []
    space = next((s for s in spaces if s["name"].lower() == space_name.lower()), None)
    if not space:
        # fuzzy fallback: partial match
        space = next((s for s in spaces if space_name.lower() in s["name"].lower()), None)
    if not space:
        return {"success": False, "error": f"Space '{space_name}' not found. Available: {[s['name'] for s in spaces]}"}

    result = supabase.table("hubs").insert({
        "name": name, "space_id": space["id"],
        "icon": icon, "color": color, "user_id": user_id,
    }).execute()
    if result.data:
        return {"success": True, "type": "hub_created",
                "label": name, "id": result.data[0]["id"],
                "space": space["name"]}
    return {"success": False, "error": "Failed to create hub"}


# Export all tools
AGENT_TOOLS = [
    create_task, update_task, create_event,
    log_expense, log_food, save_to_vault, save_report,
    create_space, create_hub,
]
