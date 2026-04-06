import json
from services.ai import get_ai_response_async
from database import supabase

MEMORY_EXTRACT_PROMPT = """
Read this conversation and extract facts about the user.
Return a JSON array. Each item: { "type": string, "content": string, "confidence": float }
Types: preference | pattern | goal | fact
Only extract genuinely useful things to remember.
Be specific. Max 5 memories per conversation.
Example: {"type":"preference","content":"prefers morning workouts","confidence":0.9}
Return [] if nothing worth remembering.
Return valid JSON only, no explanation.
"""

async def extract_and_store_memories(user_id: str, conversation: list):
    try:
        history = "\n".join([
            f"{m['role']}: {m['content'][:200]}"
            for m in conversation[-6:]
        ])
        response = await get_ai_response_async(MEMORY_EXTRACT_PROMPT, history)
        # Extract JSON array from response
        import re
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if not match:
            return
        memories = json.loads(match.group())
        for mem in memories[:5]:
            content = mem.get("content", "").strip()
            if not content:
                continue
            supabase.table("agent_memory").upsert({
                "user_id": user_id,
                "memory_type": mem.get("type", "fact"),
                "content": content,
                "confidence": float(mem.get("confidence", 0.7)),
                "last_reinforced": "now()",
            }, on_conflict="user_id,content").execute()
    except Exception:
        pass  # Silent fail — memory is enhancement not core


def get_memory_context(user_id: str) -> str:
    try:
        res = supabase.table("agent_memory") \
            .select("content, memory_type") \
            .eq("user_id", user_id) \
            .order("last_reinforced", desc=True) \
            .limit(8) \
            .execute()
        memories = res.data or []
        if not memories:
            return ""
        lines = [f"- {m['content']}" for m in memories]
        return "What you know about this user:\n" + "\n".join(lines)
    except Exception:
        return ""
