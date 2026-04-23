-- Migration: schema_v16_economy
-- Implements monetization, pricing, and creator payouts

BEGIN;

-- Add pricing to module_definitions
ALTER TABLE public.module_definitions ADD COLUMN IF NOT EXISTS price NUMERIC(10,2) DEFAULT 0;
ALTER TABLE public.module_definitions ADD COLUMN IF NOT EXISTS is_premium BOOLEAN DEFAULT false;

-- Table for creator-specific metadata (Stripe account, etc)
CREATE TABLE IF NOT EXISTS public.creator_profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  stripe_connect_id TEXT UNIQUE,
  total_earnings NUMERIC(10,2) DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Table for tracking module purchases
CREATE TABLE IF NOT EXISTS public.transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  module_def_id UUID REFERENCES public.module_definitions(id) ON DELETE CASCADE NOT NULL,
  amount_gross NUMERIC(10,2) NOT NULL,
  amount_takda_fee NUMERIC(10,2) NOT NULL, -- 30%
  amount_creator_payout NUMERIC(10,2) NOT NULL, -- 70%
  stripe_session_id TEXT UNIQUE,
  status TEXT DEFAULT 'pending', -- pending | completed | failed
  created_at TIMESTAMPTZ DEFAULT now()
);

-- RLS for creator_profiles
ALTER TABLE public.creator_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own creator profile" ON public.creator_profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own creator profile" ON public.creator_profiles FOR UPDATE USING (auth.uid() = id);

-- RLS for transactions
ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own transactions" ON public.transactions FOR SELECT USING (auth.uid() = user_id);
-- Creators can view transactions for their own modules
CREATE POLICY "Creators can view transactions for their modules" 
  ON public.transactions FOR SELECT 
  USING (EXISTS (
    SELECT 1 FROM public.module_definitions 
    WHERE id = transactions.module_def_id AND user_id = auth.uid()
  ));

COMMIT;
