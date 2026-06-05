-- Organize documents into admin-created folders (storage path: {slug}/{uuid}_{file})

CREATE TABLE IF NOT EXISTS public.document_folders (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    path VARCHAR(500) NOT NULL UNIQUE,
    parent_id INT REFERENCES public.document_folders(id) ON DELETE CASCADE,
    description TEXT DEFAULT '',
    created_by VARCHAR(50) DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE public.documents
    ADD COLUMN IF NOT EXISTS folder_id INT REFERENCES public.document_folders(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS storage_path VARCHAR(500);

INSERT INTO public.document_folders (name, slug, path, description, created_by)
SELECT 'General', 'general', 'general', 'Default folder for documents', 'system'
WHERE NOT EXISTS (SELECT 1 FROM public.document_folders WHERE path = 'general');

UPDATE public.documents
SET folder_id = (SELECT id FROM public.document_folders WHERE slug = 'general' LIMIT 1)
WHERE folder_id IS NULL;
