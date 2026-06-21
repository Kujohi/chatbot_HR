CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS vector_key TEXT,
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS embedding vector(3072),
    ADD COLUMN IF NOT EXISTS is_document BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

UPDATE document_chunks
SET vector_key = COALESCE(vector_key, chunk_id::text)
WHERE vector_key IS NULL AND chunk_id IS NOT NULL;

UPDATE document_chunks
SET vector_key = COALESCE(vector_key, 'doc-summary-' || document_id::text)
WHERE vector_key IS NULL;

ALTER TABLE document_chunks
    ALTER COLUMN vector_key SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = current_schema()
          AND indexname = 'document_chunks_vector_key_idx'
    ) THEN
        CREATE UNIQUE INDEX document_chunks_vector_key_idx ON document_chunks(vector_key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS document_chunks_document_id_idx ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS document_chunks_is_document_idx ON document_chunks(is_document);
CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx ON document_chunks USING hnsw (embedding vector_cosine_ops);
