-- Screens: custom dashboards per space
CREATE TABLE IF NOT EXISTS public.screens (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    space_id UUID NOT NULL REFERENCES public.spaces(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.screens ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own screens"
ON public.screens FOR SELECT
USING (user_id = auth.uid());

CREATE POLICY "Users can insert their own screens"
ON public.screens FOR INSERT
WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can update their own screens"
ON public.screens FOR UPDATE
USING (user_id = auth.uid());

CREATE POLICY "Users can delete their own screens"
ON public.screens FOR DELETE
USING (user_id = auth.uid());


-- Screen widgets: individual panels on a screen
CREATE TABLE IF NOT EXISTS public.screen_widgets (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    screen_id UUID NOT NULL REFERENCES public.screens(id) ON DELETE CASCADE,
    hub_id UUID REFERENCES public.hubs(id) ON DELETE CASCADE,
    type TEXT NOT NULL, -- 'tasks' | 'notes' | 'docs' | 'outcomes' | 'hub_overview'
    title TEXT,
    position INTEGER DEFAULT 0,
    config JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.screen_widgets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view widgets on their screens"
ON public.screen_widgets FOR SELECT
USING (
    screen_id IN (SELECT id FROM public.screens WHERE user_id = auth.uid())
);

CREATE POLICY "Users can insert widgets on their screens"
ON public.screen_widgets FOR INSERT
WITH CHECK (
    screen_id IN (SELECT id FROM public.screens WHERE user_id = auth.uid())
);

CREATE POLICY "Users can update widgets on their screens"
ON public.screen_widgets FOR UPDATE
USING (
    screen_id IN (SELECT id FROM public.screens WHERE user_id = auth.uid())
);

CREATE POLICY "Users can delete widgets on their screens"
ON public.screen_widgets FOR DELETE
USING (
    screen_id IN (SELECT id FROM public.screens WHERE user_id = auth.uid())
);
