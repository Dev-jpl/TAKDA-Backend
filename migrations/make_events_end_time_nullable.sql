-- ALTER events table to make end_time optional
-- Run this in your Supabase SQL Editor

ALTER TABLE public.events 
ALTER COLUMN end_time DROP NOT NULL;

-- Ensure indices for performance
CREATE INDEX IF NOT EXISTS idx_events_hub_id ON public.events(hub_id);
CREATE INDEX IF NOT EXISTS idx_events_user_id ON public.events(user_id);
