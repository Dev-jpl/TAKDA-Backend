-- Update the annotations category check constraint to allow new TAKDA categories
-- Run this in your Supabase SQL Editor

ALTER TABLE public.annotations 
DROP CONSTRAINT IF EXISTS annotations_category_check;

ALTER TABLE public.annotations 
ADD CONSTRAINT annotations_category_check 
CHECK (category IN ('idea', 'reference', 'action', 'reflection', 'insight', 'objective', 'note'));

-- Notify PostgREST to reload the schema cache
NOTIFY pgrst, 'reload schema';
