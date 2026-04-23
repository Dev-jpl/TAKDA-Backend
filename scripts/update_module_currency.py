from database import supabase
from dotenv import load_dotenv
import json
import os

load_dotenv()

def update_module():
    res = supabase.table("module_definitions").select("*").eq("slug", "expense_tracker").execute()
    if not res.data:
        print("Module not found")
        return
    
    module = res.data[0]
    layout = module["layout"]
    layout["defaultCurrency"] = "₱"
    
    res = supabase.table("module_definitions").update({"layout": layout}).eq("id", module["id"]).execute()
    if res.data:
        print("Successfully updated module definition")
    else:
        print("Failed to update module definition")

if __name__ == "__main__":
    update_module()
