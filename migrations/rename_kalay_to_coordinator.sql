-- SQL Migration: Rename legacy Kalay tables to Coordinator namespace and add professional metadata

ALTER TABLE IF EXISTS public.kalay_sessions RENAME TO coordinator_sessions;
ALTER TABLE IF EXISTS public.kalay_messages RENAME TO coordinator_messages;
ALTER TABLE IF EXISTS public.kalay_outputs RENAME TO coordinator_outputs;
ALTER TABLE IF EXISTS public.kalay_quizzes RENAME TO coordinator_quizzes;
ALTER TABLE IF EXISTS public.kalay_quiz_questions RENAME TO coordinator_quiz_questions;
ALTER TABLE IF EXISTS public.kalay_quiz_attempts RENAME TO coordinator_quiz_attempts;

-- Add updated_at if missing for active coordination tracking
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='hubs' AND column_name='updated_at') THEN
        ALTER TABLE public.hubs ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='spaces' AND column_name='updated_at') THEN
        ALTER TABLE public.spaces ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
END $$;

-- Optional: Create moddatetime trigger if it exists in your Supabase project
-- CREATE TRIGGER handle_updated_at BEFORE UPDATE ON hubs FOR EACH ROW EXECUTE PROCEDURE moddatetime (updated_at);
-- CREATE TRIGGER handle_updated_at BEFORE UPDATE ON spaces FOR EACH ROW EXECUTE PROCEDURE moddatetime (updated_at);

-- Ensure RLS and indices are preserved (PostgreSQL RENAME TO maintains these automatically)
