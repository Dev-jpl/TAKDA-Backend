-- Strava activities table
-- Run this in Supabase SQL editor after setting up Strava OAuth

CREATE TABLE IF NOT EXISTS public.strava_activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    strava_id TEXT NOT NULL,
    name TEXT,
    sport_type TEXT,                 -- Run, Ride, Swim, Walk, WeightTraining, etc.
    start_date TIMESTAMPTZ,
    distance_meters FLOAT,
    moving_time_seconds INT,
    elapsed_time_seconds INT,
    total_elevation_gain FLOAT,
    average_speed FLOAT,
    max_speed FLOAT,
    average_heartrate FLOAT,
    max_heartrate FLOAT,
    kudos_count INT DEFAULT 0,
    map_summary_polyline TEXT,
    synced_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, strava_id)
);

-- Index for fast queries by user + date
CREATE INDEX IF NOT EXISTS idx_strava_activities_user_date
    ON public.strava_activities(user_id, start_date DESC);

-- Enable RLS
ALTER TABLE public.strava_activities ENABLE ROW LEVEL SECURITY;

-- Users can only see their own activities
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'strava_activities' AND policyname = 'Users can manage their own activities'
    ) THEN
        CREATE POLICY "Users can manage their own activities"
        ON public.strava_activities
        FOR ALL
        TO authenticated
        USING (auth.uid() = user_id);
    END IF;
END
$$;

-- Also make oauth_states.code_verifier nullable so Strava can store empty string gracefully
-- (Strava doesn't use PKCE)
ALTER TABLE public.oauth_states
    ALTER COLUMN code_verifier DROP NOT NULL;
