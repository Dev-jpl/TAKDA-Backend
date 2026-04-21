-- Allow screens to exist without a parent space (user-level / cross-space screens)
ALTER TABLE public.screens ALTER COLUMN space_id DROP NOT NULL;
