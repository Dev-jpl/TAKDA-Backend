-- Migration: schema_v12_expense_item
-- Adds an 'item' column to expenses for what was purchased (separate from merchant/where)

ALTER TABLE public.expenses ADD COLUMN IF NOT EXISTS item TEXT;
