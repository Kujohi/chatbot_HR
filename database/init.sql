-- Create application-owned users table for Microsoft login sessions
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY,
    name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user', -- 'admin', 'user', etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create threads table
CREATE TABLE IF NOT EXISTS public.threads (
    id VARCHAR(50) PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    title VARCHAR(255) DEFAULT 'New Chat',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


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

-- Folders are auto-created by SharePoint sync, no default insert needed.

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    title VARCHAR(2000) NOT NULL DEFAULT '',
    source_type VARCHAR(50) NOT NULL DEFAULT '',
    file_url TEXT NOT NULL DEFAULT '',
    storage_path VARCHAR(500),
    folder_id INT NOT NULL REFERENCES document_folders(id) ON DELETE RESTRICT,
    owner_id VARCHAR(50) NOT NULL DEFAULT '',
    status VARCHAR(50) NOT NULL DEFAULT '',
    is_image_pdf BOOLEAN NOT NULL DEFAULT FALSE,
    sharepoint_item_id VARCHAR(255),
    sharepoint_modified_at TIMESTAMPTZ,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INT NOT NULL,
    chunk_id UUID,
    vector_key TEXT NOT NULL UNIQUE,
    content TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}',
    embedding vector(3072),
    is_document BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_document_chunks_document_id FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_is_document ON document_chunks(is_document);
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding ON document_chunks USING hnsw (embedding vector_cosine_ops);
