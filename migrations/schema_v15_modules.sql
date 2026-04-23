-- Migration: schema_v15_modules
-- Creates the generic Module System tables and seeds global module definitions.
-- food_logs and expenses tables are kept — backend still reads/writes them directly.

CREATE TABLE IF NOT EXISTS public.module_definitions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE,  -- NULL = system global
  slug        TEXT UNIQUE NOT NULL,
  name        TEXT NOT NULL,
  description TEXT,
  schema      JSONB DEFAULT '[]'::jsonb,
  layout      JSONB DEFAULT '{}'::jsonb,
  is_global   BOOLEAN DEFAULT false,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.module_entries (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  module_def_id UUID REFERENCES public.module_definitions(id) ON DELETE CASCADE NOT NULL,
  user_id       UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  hub_id        UUID REFERENCES public.hubs(id) ON DELETE SET NULL,
  data          JSONB DEFAULT '{}'::jsonb,
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- RLS
ALTER TABLE public.module_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.module_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "View global or own module definitions"
  ON public.module_definitions FOR SELECT
  USING (is_global = true OR auth.uid() = user_id);

CREATE POLICY "Manage own module definitions"
  ON public.module_definitions FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "View own module entries"
  ON public.module_entries FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Insert own module entries"
  ON public.module_entries FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Update own module entries"
  ON public.module_entries FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Delete own module entries"
  ON public.module_entries FOR DELETE
  USING (auth.uid() = user_id);

-- Seed global module definitions (skip if already present)
INSERT INTO public.module_definitions (slug, name, description, schema, layout, is_global)
VALUES
(
  'calorie_counter',
  'Calorie Counter',
  'Track your daily food intake and macronutrients.',
  '[
    {"key": "food_name",  "label": "Food Name",   "type": "string",   "required": true},
    {"key": "calories",   "label": "Calories",     "type": "number"},
    {"key": "protein_g",  "label": "Protein (g)",  "type": "number"},
    {"key": "carbs_g",    "label": "Carbs (g)",    "type": "number"},
    {"key": "fat_g",      "label": "Fat (g)",      "type": "number"},
    {"key": "meal_type",  "label": "Meal Type",    "type": "string"},
    {"key": "logged_at",  "label": "Logged At",    "type": "datetime", "required": true}
  ]'::jsonb,
  '{
    "type": "goal_progress",
    "goal": 2000,
    "aggregate": "calories",
    "dateField": "logged_at",
    "macros": [
      {"key": "protein_g", "label": "Protein", "goal": 150, "color": "#60a5fa"},
      {"key": "carbs_g",   "label": "Carbs",   "goal": 250, "color": "#fb923c"},
      {"key": "fat_g",     "label": "Fat",     "goal": 65,  "color": "#f472b6"}
    ]
  }'::jsonb,
  true
),
(
  'expense_tracker',
  'Expense Tracker',
  'Track your spending and expenses over time.',
  '[
    {"key": "amount",    "label": "Amount",   "type": "number", "required": true},
    {"key": "category",  "label": "Category", "type": "string"},
    {"key": "item",      "label": "Item",     "type": "string"},
    {"key": "merchant",  "label": "Merchant", "type": "string"},
    {"key": "currency",  "label": "Currency", "type": "string"},
    {"key": "date",      "label": "Date",     "type": "date",   "required": true}
  ]'::jsonb,
  '{
    "type": "trend_chart",
    "aggregate": "amount",
    "dateField": "date",
    "currencyField": "currency",
    "categoryField": "category",
    "defaultCurrency": "PHP",
    "hex": "#D85A30"
  }'::jsonb,
  true
)
ON CONFLICT (slug) DO NOTHING;
