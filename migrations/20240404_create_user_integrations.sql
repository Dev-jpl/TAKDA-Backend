-- SQL to create the user_integrations table in Supabase
-- This table stores encrypted or RLS-protected OAuth tokens for third-party services.

CREATE TABLE IF NOT EXISTS public.user_integrations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    provider TEXT NOT NULL, -- e.g., 'google'
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at TIMESTAMP WITH TIME ZONE,
    scopes TEXT[],
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(user_id, provider)
);

-- Enable RLS
ALTER TABLE public.user_integrations ENABLE ROW LEVEL SECURITY;

-- Policies
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'user_integrations' AND policyname = 'Users can manage their own integrations'
    ) THEN
        CREATE POLICY "Users can manage their own integrations" 
        ON public.user_integrations 
        FOR ALL 
        TO authenticated
        USING (auth.uid() = user_id);
    END IF;
END
$$;
