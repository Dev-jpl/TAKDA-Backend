-- Initialize the briefings table for TAKDA Intelligence Synthesis
-- Run this in your Supabase SQL Editor

CREATE TABLE IF NOT EXISTS public.briefings (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    hub_id UUID REFERENCES public.hubs(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    type TEXT DEFAULT 'daily' NOT NULL, -- 'daily', 'weekly', 'project'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS
ALTER TABLE public.briefings ENABLE ROW LEVEL SECURITY;

-- Policies
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'briefings' AND policyname = 'Users can manage their own briefings'
    ) THEN
        CREATE POLICY "Users can manage their own briefings" 
        ON public.briefings 
        FOR ALL 
        TO authenticated
        USING (auth.uid() = user_id);
    END IF;
END
$$;

-- Notify PostgREST to reload the schema cache
NOTIFY pgrst, 'reload schema';
