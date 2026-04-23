-- Create aly_memories table (missing from earlier migrations)

CREATE TABLE IF NOT EXISTS public.aly_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    content TEXT NOT NULL,
    memory_type TEXT DEFAULT 'general',  -- general | preference | fact | habit
    source TEXT,                          -- e.g. 'conversation', 'user_edit'
    embedding vector(768),
    last_reinforced TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Index for vector similarity search
CREATE INDEX IF NOT EXISTS aly_memories_embedding_idx
    ON public.aly_memories
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Index for fast user lookups
CREATE INDEX IF NOT EXISTS aly_memories_user_id_idx
    ON public.aly_memories (user_id);

-- RLS
ALTER TABLE public.aly_memories ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage their own memories"
    ON public.aly_memories
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
