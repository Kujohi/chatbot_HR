-- Run on existing databases that were created before is_image_pdf existed.
ALTER TABLE public.documents
ADD COLUMN IF NOT EXISTS is_image_pdf BOOLEAN NOT NULL DEFAULT FALSE;
