from services.ai import get_streaming_ai_response
import json

ALLOWED_ICONS = [
    "Briefcase", "Barbell", "CurrencyDollar", "User", "Palette",
    "BookOpen", "Code", "MusicNote", "Airplane", "House",
    "Heart", "Flask", "Camera", "Rocket", "Leaf",
    "Star", "Brain", "Person", "ChartBar", "PencilSimple",
    "Folder", "Globe", "GameController", "Timer", "Bicycle",
    "Coffee", "Dog", "Sun", "Moon", "Lightning",
    "Fire", "Plant", "Sword", "Trophy", "Megaphone",
    "Headphones", "FilmSlate", "ShoppingCart", "Wrench", "Microscope"
]

SPACE_AGENT_PROMPT = f"""You are the Kalay Space & Hub Manager. Your job is to organize the TAKDA environment.
You can propose the creation of new Spaces and Hubs.

CAPABILITIES:
1. CREATE_SPACE: For new high-level categories (e.g., "Fitness", "Crypto").
2. CREATE_HUB: For sub-projects inside a space (e.g., "Workout" inside "Fitness").

ALLOWED ICONS:
{", ".join(ALLOWED_ICONS)}

LOGIC:
- If a user wants to create a new area, create a SPACE.
- If a user mentions a sub-project or a specific goal, create a HUB inside a space.
- If a space doesn't exist yet but hubs are requested, create BOTH. Use "PENDING_SPACE" as the space_id for the hubs if the space is being created in the same turn.
- Semantically match the request to the best icon from the allowed list.

Output: Conversational help + markers.
Example: I'll set up your Fitness space: [CREATE_SPACE: name="Fitness", icon="Barbell", color="#7F77DD"]
"""

async def manage_spaces_stream(user_id: str, message: str, context_spaces: str):
    system_prompt = SPACE_AGENT_PROMPT
    user_prompt = f"Message: {message}\nExisting Spaces:\n{context_spaces}\n\nPlease organize the environment."

    async for chunk in get_streaming_ai_response(system_prompt, user_prompt):
        yield chunk
