-- Create users table extending Supabase auth
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user', -- 'admin', 'user', etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Function to handle new user signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, name, role)
  VALUES (
    new.id,
    new.raw_user_meta_data->>'full_name',
    'user' -- Default role
  );
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger for new user signup
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Create threads table
CREATE TABLE IF NOT EXISTS public.threads (
    id VARCHAR(50) PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    title VARCHAR(255) DEFAULT 'New Chat',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

DROP TABLE IF EXISTS chat_conversations;

CREATE TABLE chat_conversations (
    id SERIAL PRIMARY KEY,
    thread_id VARCHAR(50) NOT NULL REFERENCES public.threads(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL DEFAULT '',
    content TEXT,
    is_request BOOLEAN DEFAULT TRUE,
    completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DROP TABLE IF EXISTS document_chunks;
DROP TABLE IF EXISTS documents;

CREATE TABLE document_folders (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    path VARCHAR(500) NOT NULL UNIQUE,
    parent_id INT REFERENCES document_folders(id) ON DELETE CASCADE,
    description TEXT DEFAULT '',
    created_by VARCHAR(50) DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO document_folders (name, slug, path, description, created_by)
VALUES ('General', 'general', 'general', 'Default folder for documents', 'system');

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    title VARCHAR(2000) NOT NULL DEFAULT '',
    source_type VARCHAR(50) NOT NULL DEFAULT '',
    file_url VARCHAR(500) NOT NULL DEFAULT '',
    storage_path VARCHAR(500),
    folder_id INT NOT NULL REFERENCES document_folders(id) ON DELETE RESTRICT,
    owner_id VARCHAR(50) NOT NULL DEFAULT '',
    status VARCHAR(50) NOT NULL DEFAULT '',
    is_image_pdf BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INT NOT NULL,
    chunk_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000',
    content TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_document_chunks_document_id FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
