-- Create space_tools table
CREATE TABLE IF NOT EXISTS public.space_tools (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    space_id UUID NOT NULL REFERENCES public.spaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL, -- 'webhook', 'api_key', 'oauth', 'custom'
    config JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- RLS policies
ALTER TABLE public.space_tools ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view tools in their spaces" 
ON public.space_tools FOR SELECT 
USING (
    space_id IN (
        SELECT id FROM public.spaces WHERE user_id = auth.uid()
    )
);

CREATE POLICY "Users can insert tools in their spaces" 
ON public.space_tools FOR INSERT 
WITH CHECK (
    space_id IN (
        SELECT id FROM public.spaces WHERE user_id = auth.uid()
    )
);

CREATE POLICY "Users can update tools in their spaces" 
ON public.space_tools FOR UPDATE 
USING (
    space_id IN (
        SELECT id FROM public.spaces WHERE user_id = auth.uid()
    )
);

CREATE POLICY "Users can delete tools in their spaces" 
ON public.space_tools FOR DELETE 
USING (
    space_id IN (
        SELECT id FROM public.spaces WHERE user_id = auth.uid()
    )
);
