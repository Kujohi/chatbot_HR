-- Nested folders: parent_id + full storage path (e.g. general/hr-policies)

ALTER TABLE public.document_folders
  ADD COLUMN IF NOT EXISTS parent_id INT REFERENCES public.document_folders(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS path VARCHAR(500);

UPDATE public.document_folders
SET path = slug
WHERE path IS NULL OR path = '';

ALTER TABLE public.document_folders DROP CONSTRAINT IF EXISTS document_folders_slug_key;

CREATE UNIQUE INDEX IF NOT EXISTS document_folders_path_unique
  ON public.document_folders (path);
