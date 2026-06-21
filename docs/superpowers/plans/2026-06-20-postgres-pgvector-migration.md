# Postgres + pgvector Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Supabase and Pinecone with internal PostgreSQL + pgvector while preserving the current flow: Microsoft login, SharePoint as the source file system, document browsing, chat history, and RAG behavior.

**Architecture:** The backend becomes the owner of auth/session state, relational persistence, and vector search. SharePoint remains the source of truth for files, so the document ingestion flow stays conceptually the same: fetch file metadata from SharePoint, read the file from its URL, extract text, store metadata in PostgreSQL, and store embeddings in pgvector. The deployment must include an internal PostgreSQL service or a clearly defined internal managed PostgreSQL target, plus a migration/bootstrap path that can initialize a fresh database without any Supabase schema. The frontend keeps the same user-facing screens and routes, but it stops talking directly to Supabase and instead talks to backend endpoints for auth, profile, threads, and conversation data.

**Tech Stack:** FastAPI, PostgreSQL, pgvector, Python, Next.js, React, TypeScript, Microsoft Entra ID/MSAL.

**Non-Goals / Hard Constraints:** Do not change the core product flow outside the data layer migration. Keep Microsoft login as the auth experience. Keep SharePoint as the only source of file truth. Keep Gemini for embeddings and LLM responses. Do not replace or redesign the chat UX, document browsing UX, sync cadence, retrieval prompting, or citation format unless a step explicitly requires it for the Supabase/Pinecone migration.

---

### Task 1: Replace Supabase database access with internal PostgreSQL access

**Files:**
- Create: `backend/src/db/postgres.py`
- Create: `backend/src/db/repositories/users.py`
- Create: `backend/src/db/repositories/threads.py`
- Create: `backend/src/db/repositories/conversations.py`
- Create: `backend/src/db/repositories/documents.py`
- Create: `backend/src/db/repositories/folders.py`
- Modify: `backend/src/db/client.py`
- Modify: `backend/src/services/conversation.py`
- Modify: `backend/src/services/folder_service.py`
- Modify: `backend/src/services/document_service.py`
- Modify: `backend/src/services/document_processing_service.py`
- Modify: `backend/src/api/routes.py`
- Modify: `database/init.sql`
- Create: `database/migrations/20260620_remove_supabase_auth.sql`

- [ ] **Step 1: Add the PostgreSQL schema changes**

Split the database setup into two parts:
- `database/init.sql` becomes the fresh-database bootstrap for an internal PostgreSQL instance and must not reference `auth.users`
- `database/migrations/20260620_remove_supabase_auth.sql` handles one-time cleanup on databases that were previously bootstrapped by Supabase

Fresh bootstrap SQL should look like:

```sql
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY,
    name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

The cleanup migration should safely drop Supabase-auth objects only when they exist, without touching any other `auth` objects:

```sql
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'auth' AND table_name = 'users'
  ) THEN
    DROP TABLE auth.users CASCADE;
  END IF;
END $$;

DROP FUNCTION IF EXISTS public.handle_new_user();
```

Keep the existing `threads`, `chat_conversations`, `document_folders`, `documents`, and `document_chunks` tables, but remove any dependence on `auth.users`.

- [ ] **Step 2: Add a thin PostgreSQL connection helper**

Implement a small connection/pool helper in `backend/src/db/postgres.py` that returns a reusable connection and a cursor wrapper for `SELECT`, `INSERT`, `UPDATE`, and `DELETE` operations.

Expected behavior:
- The backend can query `users`, `threads`, `chat_conversations`, `documents`, `document_folders`, and `document_chunks` without Supabase.
- Existing service logic can be migrated one table at a time instead of rewriting all flows at once.

- [ ] **Step 3: Rewrite conversation, folder, and document service calls**

Move the data access logic from Supabase query chains into repository functions:
- `backend/src/services/conversation.py` should insert and list conversation rows through `conversations.py`.
- `backend/src/services/folder_service.py` should list folders and build breadcrumbs through `folders.py`.
- `backend/src/services/document_service.py` should load documents, chunks, and references through `documents.py`.
- `backend/src/services/document_processing_service.py` should store chunks through the new repository helpers.

Keep function names and return shapes stable where possible so the rest of the backend does not need logic changes.

- [ ] **Step 4: Update backend routes to call repositories instead of Supabase**

Replace direct `get_supabase()` usage in `backend/src/api/routes.py` with repository functions for:
- thread deletion
- document view lookup
- folder listing
- document listing
- chunk lookup

Expected behavior:
- The `/health`, `/folders`, `/documents`, `/chunk/{id}`, `/chat/conversation/{thread_id}`, and `/documents/{document_id}/view` routes still exist.
- Their responses stay compatible with the current frontend.

- [ ] **Step 5: Validate the database layer**

Run:

```bash
python -m py_compile backend/src/db/*.py backend/src/services/*.py backend/src/api/routes.py
```

Expected:
- No syntax errors.
- No remaining hard dependency on Supabase table clients inside backend service code.
- The bootstrap path can initialize a fresh internal PostgreSQL database without Supabase schema objects.

---

### Task 1.5: Add an internal PostgreSQL runtime target

**Files:**
- Modify: `docker-compose.yml`
- Modify: `backend/.env`
- Modify: `backend/Dockerfile`
- Modify: `README.md`

- [ ] **Step 1: Define where PostgreSQL runs**

Add an explicit PostgreSQL service to `docker-compose.yml` for local development so the migrated app can run end-to-end without Supabase.

Expected behavior:
- `DATABASE_URL` points to the internal PostgreSQL instance.
- The backend can connect to that instance on startup.
- Fresh local environments do not depend on Supabase being present.
- Production can still point `DATABASE_URL` at a managed internal PostgreSQL target if desired, but the schema and behavior must stay identical.

- [ ] **Step 2: Make sure pgvector is available in the database**

Use a PostgreSQL image that supports `pgvector` for the local compose service, then apply the extension during bootstrap.

Expected behavior:
- `CREATE EXTENSION IF NOT EXISTS vector;` succeeds on a fresh database.

- [ ] **Step 3: Wire migration/bootstrap application into startup docs**

Document exactly how the internal PostgreSQL schema is created:
- first-time bootstrap for a new database
- one-time Supabase-auth cleanup for existing migrated databases
- pgvector extension installation
- local compose startup order: PostgreSQL, backend, frontend, nginx
- the local PostgreSQL service must run the bootstrap SQL automatically on first startup, either through the image's init directory or a one-shot migration runner started by compose

- [ ] **Step 4: Validate the DB runtime contract**

Run:

```bash
docker compose config
```

Expected:
- The compose file still represents a valid runtime topology.
- Any PostgreSQL service or external DB contract is explicit, not implied.

---

### Task 2: Move Microsoft login off Supabase while keeping the same user experience

**Files:**
- Modify: `frontend/src/components/ChatUI.tsx`
- Modify: `frontend/src/lib/supabase.ts`
- Modify: `frontend/src/lib/runtime-config.ts`
- Modify: `frontend/src/app/layout.tsx`
- Create: `backend/src/api/auth_routes.py`
- Create: `backend/src/services/auth_service.py`
- Modify: `backend/src/api/routes.py`
- Modify: `backend/src/db/test.py`

- [ ] **Step 1: Define the backend auth contract**

Expose backend endpoints for:
- Microsoft login start
- Microsoft callback
- current user lookup
- logout

The backend should create or update a row in `users` after Microsoft login and then issue a session cookie or JWT that the frontend uses for subsequent requests.

- [ ] **Step 2: Remove frontend direct Supabase auth usage**

Replace these frontend behaviors:
- `supabase.auth.getSession()`
- `supabase.auth.onAuthStateChange(...)`
- `supabase.auth.signInWithOAuth({ provider: 'azure' })`
- `supabase.auth.signOut()`
- `supabase.from('users')`
- `supabase.from('threads')`

Keep the same visible login button and the same signed-in UI state.

- [ ] **Step 3: Replace thread creation and profile loading with backend calls**

The frontend should fetch:
- current user profile from the backend
- thread list from the backend
- current conversation history from the backend

Expected behavior:
- The user still signs in with Microsoft.
- The sidebar still shows the user name, role, and thread list.
- No browser-side Supabase client is needed anymore.

- [ ] **Step 4: Validate auth flow without changing UI behavior**

Run:

```bash
npm run lint --prefix frontend
```

Expected:
- No new lint errors from auth-state changes.
- The login screen still renders for unauthenticated users.
- The signed-in UI still renders for authenticated users.

---

### Task 3: Replace Pinecone with pgvector while keeping the same RAG flow

**Files:**
- Modify: `backend/src/services/document_processing_service.py`
- Modify: `backend/src/services/retrieval_service.py`
- Modify: `backend/src/services/document_service.py`
- Modify: `backend/src/services/rag_service.py`
- Modify: `backend/src/vector_db.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/src/db/client.py`
- Modify: `database/init.sql`
- Create: `backend/src/db/repositories/vector_store.py`
- Create: `database/migrations/20260620_add_pgvector.sql`

- [ ] **Step 1: Add the pgvector extension and vector columns**

Add a migration that enables `pgvector` and gives the app a place to store:
- document summary embeddings
- chunk embeddings

Keep the existing `document_chunks.content` and `document_chunks.metadata` fields so the citation and source-link behavior does not change.
Store summary embeddings in a new `documents.summary_embedding` vector column and chunk embeddings in a new `document_chunks.embedding` vector column so the retrieval path stays close to the current document/chunk model.

- [ ] **Step 2: Move embedding writes into Postgres**

Replace Pinecone writes in `document_processing_service.py` and `document_service.py` with inserts/updates into the pgvector-backed table or columns.

Keep the same indexing semantics:
- document summary vectors still route queries to relevant files
- chunk vectors still support top-k semantic retrieval
- delete/rollback paths still clean up vectors when a document changes or is removed

- [ ] **Step 3: Move retrieval queries into Postgres similarity search**

Replace Pinecone similarity search in `retrieval_service.py` with pgvector similarity queries.

Expected behavior:
- `search_document_summaries(...)` still returns relevant `storage_path` values.
- `search_text_chunks(...)` still scopes chunk retrieval to the selected documents.
- `search_documents(...)` still splits between text PDFs and scanned PDFs exactly as before.

- [ ] **Step 4: Keep the RAG prompt and citation rules unchanged**

Do not change:
- `backend/src/services/llm.py`
- the text citation format
- the scanned-PDF citation format
- the `rag_service.py` prompt structure

Only change how retrieval produces the retrieved context.

- [ ] **Step 5: Validate vector search behavior**

Run:

```bash
python -m py_compile backend/src/services/*.py backend/src/vector_db.py
```

Then smoke-test one indexed document and one chat query.

Expected:
- The system still answers from retrieved context.
- Citations still point to the same chunk/document references.
- No Pinecone calls remain in the retrieval or indexing path.

---

### Task 4: Keep SharePoint storage and document viewing behavior intact

**Files:**
- Modify: `backend/src/services/sharepoint_sync_service.py`
- Modify: `backend/src/services/image_document_service.py`
- Modify: `backend/src/api/routes.py`
- Modify: `frontend/src/components/ChatUI.tsx`
- Modify: `README.md`

- [ ] **Step 1: Leave SharePoint as the source of file truth**

Do not introduce a new storage system in this migration.

Keep the existing SharePoint sync flow so:
- files still come from SharePoint
- `file_url` still points to the source file
- `storage_path` still represents the logical folder path

- [ ] **Step 2: Preserve document view redirect behavior**

Keep `/documents/{document_id}/view` redirecting to the available file URL or SharePoint web URL.

Expected behavior:
- The document browser still opens the original file.
- Scanned PDFs still load correctly for vision-based references.

- [ ] **Step 3: Leave the sync cadence and document browser UX unchanged**

The automatic sync, manual sync, folder tree, and document list should still behave the same from the user’s point of view.

- [ ] **Step 4: Update README text so it matches the code**

Update documentation that currently implies Supabase Storage is the file source so it clearly says SharePoint remains the source of file truth.

---

### Task 5: End-to-end verification and rollout

**Files:**
- Modify: `frontend/.env.local`
- Modify: `backend/.env`
- Modify: `docker-compose.yml`
- Modify: `start.sh`
- Modify: `deploy/nginx/default.conf`
- Modify: `README.md`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Update environment variables for internal services**

Remove Supabase and Pinecone env vars from the runtime contract.
Add the internal PostgreSQL connection string and the pgvector-related configuration.

Keep Microsoft and SharePoint env vars intact.

- [ ] **Step 2: Keep the deployment topology the same**

Do not change the current runtime shape:
- frontend stays Next.js
- backend stays FastAPI
- Nginx still reverse-proxies the two services

Only swap the data/auth/vector dependencies behind those services.

- [ ] **Step 3: Run a full local smoke test**

Run:

```bash
docker compose up --build
```

Then verify:
- frontend loads
- Microsoft login starts and returns to the app
- chat history loads
- folder/document browsing works
- document view opens
- sync still runs
- a sample question still retrieves relevant context from pgvector-backed search

- [ ] **Step 4: Clean up leftover Supabase and Pinecone references**

Search the repo for remaining references and remove or replace any code paths that still assume:
- Supabase auth
- Supabase table client usage
- Pinecone indexes

Run:

```bash
rg -n "supabase|PINECONE|pinecone" backend frontend database README.md
```

Expected:
- Only intentional documentation references remain, if any.

- [ ] **Step 5: Remove unused client and provider dependencies**

Remove `@supabase/supabase-js` from the frontend dependency list, and remove `supabase`, `pinecone`, and `langchain-pinecone` from the backend requirements file.

Expected:
- The frontend package manifest no longer advertises a Supabase client that the app does not use.
- The backend requirements no longer advertise Pinecone or Supabase libraries that the app does not use.
