-- Migration: schema_v9_hub_addons
-- Addon registry: installable data modules per hub

CREATE TABLE IF NOT EXISTS public.hub_addons (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hub_id UUID REFERENCES public.hubs(id) ON DELETE CASCADE NOT NULL,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  type TEXT NOT NULL,        -- 'calorie_counter' | 'expense_tracker' | 'habit_tracker'
  config JSONB DEFAULT '{}', -- per-addon settings (e.g. {"calorie_goal": 2000})
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(hub_id, type)       -- one instance per type per hub
);

-- Enable RLS
ALTER TABLE public.hub_addons ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own hub addons"
  ON public.hub_addons FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own hub addons"
  ON public.hub_addons FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own hub addons"
  ON public.hub_addons FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own hub addons"
  ON public.hub_addons FOR DELETE
  USING (auth.uid() = user_id);
