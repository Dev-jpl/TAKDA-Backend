-- Phase 1 Foundation Migration

-- 1. Create user_profiles
CREATE TABLE IF NOT EXISTS public.user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    context_bio TEXT,
    nav_pins JSONB DEFAULT '[]'::jsonb,
    home_screen_id UUID,
    wellbeing_prefs JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Note: home_screen_id reference will be added later or assuming screens exists
-- ALTER TABLE public.user_profiles ADD CONSTRAINT fk_home_screen FOREIGN KEY (home_screen_id) REFERENCES public.screens(id) ON DELETE SET NULL;

-- 2. Alter embedding dimensions to 768
-- Note: PostgreSQL pgvector doesn't support altering dimensions directly if data exists,
-- so we alter type. If it fails due to existing data, it would require a multi-step drop.
-- We use a simple ALTER TYPE which works if the column is empty or we drop data.
-- To be safe, we will drop the embedding columns and recreate them as 768.

ALTER TABLE public.annotations DROP COLUMN IF EXISTS embedding;
ALTER TABLE public.annotations ADD COLUMN embedding vector(768);

ALTER TABLE public.document_chunks DROP COLUMN IF EXISTS embedding;
ALTER TABLE public.document_chunks ADD COLUMN embedding vector(768);

ALTER TABLE public.aly_memories DROP COLUMN IF EXISTS embedding;
ALTER TABLE public.aly_memories ADD COLUMN embedding vector(768);

-- 3. Recreate vector matching functions for 768

CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding vector(768),
    match_count int DEFAULT null,
    user_id uuid DEFAULT null,
    document_ids uuid[] DEFAULT null
)
RETURNS TABLE(
    id uuid,
    document_id uuid,
    content text,
    chunk_index int,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        dc.id,
        dc.document_id,
        dc.content,
        dc.chunk_index,
        1 - (dc.embedding <=> query_embedding) AS similarity
    FROM document_chunks dc
    JOIN documents d ON dc.document_id = d.id
    WHERE (user_id IS NULL OR d.user_id = match_chunks.user_id)
      AND (document_ids IS NULL OR dc.document_id = ANY(document_ids))
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function for matching annotations
CREATE OR REPLACE FUNCTION match_annotations(
    query_embedding vector(768),
    match_count int DEFAULT null,
    target_user_id uuid DEFAULT null,
    hub_ids uuid[] DEFAULT null
)
RETURNS TABLE(
    id uuid,
    hub_id uuid,
    content text,
    category text,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.id,
        a.hub_id,
        a.content,
        a.category,
        1 - (a.embedding <=> query_embedding) AS similarity
    FROM annotations a
    WHERE (target_user_id IS NULL OR a.user_id = target_user_id)
      AND (hub_ids IS NULL OR a.hub_id = ANY(hub_ids))
    ORDER BY a.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function for matching memories
CREATE OR REPLACE FUNCTION match_memories(
    query_embedding vector(768),
    match_count int DEFAULT null,
    target_user_id uuid DEFAULT null
)
RETURNS TABLE(
    id uuid,
    content text,
    memory_type text,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.id,
        m.content,
        m.memory_type,
        1 - (m.embedding <=> query_embedding) AS similarity
    FROM aly_memories m
    WHERE (target_user_id IS NULL OR m.user_id = target_user_id)
    ORDER BY m.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
