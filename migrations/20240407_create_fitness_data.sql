-- SQL to create the user_fitness_data table in Supabase
-- This table stores daily summaries of fitness data.

CREATE TABLE IF NOT EXISTS public.user_fitness_data (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    date DATE NOT NULL, -- Daily aggregation
    steps INTEGER DEFAULT 0,
    calories_burned FLOAT DEFAULT 0,
    distance_meters FLOAT DEFAULT 0,
    avg_heart_rate FLOAT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(user_id, date)
);

-- Enable RLS
ALTER TABLE public.user_fitness_data ENABLE ROW LEVEL SECURITY;

-- Policies
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'user_fitness_data' AND policyname = 'Users can manage their own fitness data'
    ) THEN
        CREATE POLICY "Users can manage their own fitness data" 
        ON public.user_fitness_data 
        FOR ALL 
        TO authenticated
        USING (auth.uid() = user_id);
    END IF;
END
$$;

-- Reload PostgREST
NOTIFY pgrst, 'reload schema';
