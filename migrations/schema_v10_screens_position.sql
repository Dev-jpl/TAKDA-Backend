-- schema_v10_screens_position.sql
-- Add position ordering for customized user dashboard ordering

ALTER TABLE public.screens ADD COLUMN position INTEGER DEFAULT 0;
