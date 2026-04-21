-- Migration: schema_v11_expenses
-- Creates the expenses table used by Expense Tracker addon and Aly's log_expense tool

CREATE TABLE IF NOT EXISTS public.expenses (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  hub_id      UUID REFERENCES public.hubs(id) ON DELETE SET NULL,  -- nullable: Aly may log without a hub
  amount      FLOAT NOT NULL,
  merchant    TEXT,
  category    TEXT NOT NULL DEFAULT 'General',
  currency    TEXT NOT NULL DEFAULT 'PHP',
  date        DATE NOT NULL DEFAULT CURRENT_DATE,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- Fast lookups by user + date range
CREATE INDEX IF NOT EXISTS idx_expenses_user_date
  ON public.expenses(user_id, date DESC);

-- Fast lookups by hub + date range
CREATE INDEX IF NOT EXISTS idx_expenses_hub_date
  ON public.expenses(hub_id, date DESC);

-- Enable RLS
ALTER TABLE public.expenses ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own expenses"
  ON public.expenses FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own expenses"
  ON public.expenses FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own expenses"
  ON public.expenses FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own expenses"
  ON public.expenses FOR DELETE
  USING (auth.uid() = user_id);
