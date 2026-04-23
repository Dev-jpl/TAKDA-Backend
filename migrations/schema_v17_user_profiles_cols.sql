-- Migration: schema_v17_user_profiles_cols
-- Adds missing columns to user_profiles for deployments where the table
-- pre-existed before schema_v13 (CREATE TABLE IF NOT EXISTS skipped them).

ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS nav_pins       JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS home_screen_id UUID,
  ADD COLUMN IF NOT EXISTS wellbeing_prefs JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS context_bio    TEXT;
