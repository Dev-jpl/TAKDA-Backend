-- SQL to initialize the world-class Calendar V2 Architecture in Supabase
-- Run this in your Supabase SQL Editor

-- 1. External Accounts (multi-provider ready)
CREATE TABLE IF NOT EXISTS public.external_accounts (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    provider TEXT NOT NULL,         -- 'google', 'apple', 'outlook'
    email TEXT NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

-- 2. Calendars (Abstraction Layer)
CREATE TABLE IF NOT EXISTS public.calendars (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    external_account_id UUID REFERENCES public.external_accounts(id) ON DELETE SET NULL,
    provider_calendar_id TEXT,      -- e.g. Google's 'primary' or Cal ID
    name TEXT NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

-- 3. Update events table for V2 (Safe renaming)
DO $$ 
BEGIN
    -- Rename start column if needed
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='events' AND column_name='start_time') THEN
        ALTER TABLE public.events RENAME COLUMN start_time TO start_at;
    ELSIF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='events' AND column_name='date_from') THEN
        ALTER TABLE public.events RENAME COLUMN date_from TO start_at;
    END IF;

    -- Rename end column if needed
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='events' AND column_name='end_time') THEN
        ALTER TABLE public.events RENAME COLUMN end_time TO end_at;
    ELSIF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='events' AND column_name='date_to') THEN
        ALTER TABLE public.events RENAME COLUMN date_to TO end_at;
    END IF;
END $$;

ALTER TABLE public.events ADD COLUMN IF NOT EXISTS people TEXT;
ALTER TABLE public.events ADD COLUMN IF NOT EXISTS location TEXT;
ALTER TABLE public.events ADD COLUMN IF NOT EXISTS calendar_id UUID REFERENCES public.calendars(id) ON DELETE SET NULL;

-- 4. Reload PostgREST schema cache
NOTIFY pgrst, 'reload schema';

-- 5. Event Sync Mapping
CREATE TABLE IF NOT EXISTS public.event_sync (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    event_id UUID REFERENCES public.events(id) ON DELETE CASCADE NOT NULL,
    external_account_id UUID REFERENCES public.external_accounts(id) ON DELETE CASCADE NOT NULL,
    provider_event_id TEXT NOT NULL,
    last_synced_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

-- Enable RLS for new tables
ALTER TABLE public.external_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.calendars ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_sync ENABLE ROW LEVEL SECURITY;

-- Dynamic Policies for V2
CREATE POLICY "Users can manage their own external accounts" ON public.external_accounts FOR ALL TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Users can manage their own calendars" ON public.calendars FOR ALL TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Users can manage their own sync mappings" ON public.event_sync FOR ALL TO authenticated USING (
    EXISTS (SELECT 1 FROM public.events e WHERE e.id = event_id AND e.user_id = auth.uid())
);
