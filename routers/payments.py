from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from database import supabase
import uuid

router = APIRouter(prefix="/payments", tags=["payments"])

class CheckoutSessionBody(BaseModel):
    module_def_id: str
    user_id: str

@router.post("/create-checkout-session")
async def create_checkout_session(body: CheckoutSessionBody):
    """Mocks Stripe Checkout session creation."""
    # Fetch module price
    res = supabase.table("module_definitions").select("price,name").eq("id", body.module_def_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Module not found")
    
    module = res.data
    price = float(module["price"])
    
    if price <= 0:
        return {"url": f"/marketplace/success?id={body.module_def_id}"}

    # In a real app, you would use stripe.checkout.Session.create(...)
    mock_session_id = f"mock_cs_{uuid.uuid4()}"
    
    # Record pending transaction
    supabase.table("transactions").insert({
        "user_id": body.user_id,
        "module_def_id": body.module_def_id,
        "amount_gross": price,
        "amount_takda_fee": price * 0.3,
        "amount_creator_payout": price * 0.7,
        "stripe_session_id": mock_session_id,
        "status": "pending"
    }).execute()

    # We return a mock success URL that simulates a redirect back from Stripe
    return {"url": f"/marketplace/success?session_id={mock_session_id}&id={body.module_def_id}"}

@router.post("/confirm-purchase")
async def confirm_purchase(session_id: str):
    """Mocks the Stripe webhook / return URL processing."""
    # Find the transaction
    res = supabase.table("transactions").select("*").eq("stripe_session_id", session_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    transaction = res.data
    if transaction["status"] == "completed":
        return {"status": "already_completed"}

    # Update transaction status
    supabase.table("transactions").update({"status": "completed"}).eq("id", transaction["id"]).execute()
    
    # Update creator earnings
    module_res = supabase.table("module_definitions").select("user_id").eq("id", transaction["module_def_id"]).single().execute()
    if module_res.data and module_res.data["user_id"]:
        creator_id = module_res.data["user_id"]
        # Increment total_earnings in creator_profiles
        supabase.rpc("increment_creator_earnings", {"creator_id": creator_id, "amount": float(transaction["amount_creator_payout"])}).execute()

    return {"status": "success"}
