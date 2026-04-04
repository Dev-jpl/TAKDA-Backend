-- Create oauth_states table for temporary storage of PKCE verifiers
CREATE TABLE IF NOT EXISTS public.oauth_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    code_verifier TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Add index for cleanup
CREATE INDEX idx_oauth_states_created_at ON public.oauth_states(created_at);

-- Add RLS (Service role only recommended, but we'll add basic policies)
ALTER TABLE public.oauth_states ENABLE ROW LEVEL SECURITY;

-- Allow the backend to manage states (if using anon/authenticated, but backend should use service_role)
CREATE POLICY "Service role can manage all states" ON public.oauth_states
    FOR ALL USING (true) WITH CHECK (true);
