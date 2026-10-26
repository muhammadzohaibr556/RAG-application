# Build journal

The implementation follows these milestones in order. Each entry is a learning checkpoint;
you can run its manual checks against the finished application. Later milestones extend
the same upload endpoint rather than introducing temporary public endpoints.

## 1 — Application foundation

**Implemented:** FastAPI lifespan, PostgreSQL metadata models and readiness check,
Next.js/React/TypeScript shell, environment configuration, Docker images and Compose.

**Files:** `compose.yaml`, `.env.example`, `backend/Dockerfile`, `backend/requirements*.txt`,
`backend/pyproject.toml`, `backend/app/{config,database,errors,main}.py`, and
`frontend/{Dockerfile,package.json,package-lock.json,tsconfig.json,next.config.ts,app/layout.tsx,app/page.tsx}`.

**How it works:** Compose waits for PostgreSQL, then starts one API worker and the UI.
SQLAlchemy creates the initial schema at startup; `/health` checks a real database connection.

**Manual check:** Copy `.env.example` to `.env`, then `docker compose up --build`.
Open `http://localhost:3000` and `http://localhost:8000/docs`; run
`curl http://localhost:8000/health`. Docker must be installed and running.

**Before moving on:** Understand an HTTP route, database session/transaction, environment
variables, container DNS (`db` versus `localhost`), and Docker named volumes.

## 2 — Upload boundary

**Implemented:** Extension/MIME allowlist, basename sanitization, empty-file rejection,
bounded reads, automatic file closing, and typed public exceptions.

**Files:** `backend/app/uploads.py`, `backend/tests/test_uploads.py`.

**How it works:** `read_upload` converts FastAPI's multipart file into a bounded bytes
value. No user-supplied filename is ever used as a storage path. The endpoint is wired
to the completed ingestion service in milestone 6, so incomplete documents never appear ready.

**Manual check:** Run `cd backend && ../.venv/bin/pytest tests/test_uploads.py`.
In the finished API, upload with `curl -F 'file=@samples/permit.txt;type=text/plain'
http://localhost:8000/api/documents/upload`. Repeat with `type=application/pdf` to see rejection.
Run this curl command from the repository root.

**Before moving on:** Understand multipart uploads, MIME versus file extension,
untrusted filenames, and why MIME validation alone cannot validate file contents.

## 3 — Extraction and normalization

**Implemented:** PyMuPDF pages, python-docx body paragraphs/table cells, UTF-8 TXT lines,
empty/scanned-file rejection, decompression/text limits, and whitespace normalization.

**Files:** `backend/app/extraction.py`, `backend/app/normalization.py`,
`backend/tests/test_extraction.py`.

**How it works:** Each `TextUnit` carries its original one-based position. Normalization
can drop blank units without renumbering the remaining ones. PDF pages remain separate.
DOCX paragraph numbers refer to body XML order, including empty paragraphs and table cells.

**Manual check:** Run `pytest tests/test_extraction.py` from `backend` with the venv active.
In the final API, upload a two-page PDF, a Word file with blank paragraphs, and a TXT with
blank lines. Search their distinctive phrases and inspect the returned coordinates.
Try an image-only PDF: it should return a clear 400 error rather than quietly ingesting it.

**Before moving on:** Extraction is format parsing, not semantic understanding. Reading
order can be imperfect in columns; normalization must preserve the mapping back to the source.

## 4 — Token chunking

**Implemented:** Configurable 700-token windows and 120-token overlap using tiktoken,
Unicode-safe character boundaries, and original source-range mapping.

**Files:** `backend/app/chunking.py`, `backend/tests/test_chunking.py`.

**How it works:** Token positions map to character offsets, which map to source units.
Each PDF page is chunked separately. DOCX/TXT windows may span paragraphs/lines;
their first and last original positions are stored. A short final window is kept.

**Manual check:** Run `pytest tests/test_chunking.py`. Change `CHUNK_SIZE=100` and
`CHUNK_OVERLAP=20`, restart the backend, and upload a long TXT. Inspect `chunk_count`
and `/api/search` results. Existing documents retain their original chunks.

**Before moving on:** A token is not a word. Overlap retains boundary context but costs
additional embeddings and can produce duplicate evidence. Unicode-safe boundaries make
the token budget approximate by a few tokens in some scripts.

## 5 — Embeddings

**Implemented:** A small typed embedding interface, OpenAI adapter, bounded batches,
response-order restoration, vector validation, and safe provider errors.

**Files:** `backend/app/embeddings.py`, `backend/tests/test_embeddings.py`.

**How it works:** Each chunk becomes one float32 vector. The same model and dimensions
embed questions later. The default is `text-embedding-3-small` with 1536 dimensions.
OpenAI is called directly; no high-level RAG framework is involved.

**Manual check:** Run `pytest tests/test_embeddings.py` without a key. For a live check,
set `OPENAI_API_KEY`, restart, upload the sample, and look for `embeddings generated`
in backend logs. This sends document text to OpenAI and uses your API quota.

**Before moving on:** Similar meanings tend to have nearby vectors. Vector coordinates
are not words or probabilities. Never compare vectors from different embedding models.

## 6 — FAISS storage and ingestion

**Implemented:** Normalized `IndexFlatIP` wrapped in `IndexIDMap2`, disk snapshots,
embedding-model fingerprint, process/thread locks, crash reconciliation, ingestion, deletion.

**Files:** `backend/app/vector_store.py`, `backend/app/ingestion.py`,
`backend/tests/test_vector_store.py`. API wiring is in `backend/app/main.py`.

**How it works:** SQLAlchemy flush assigns chunk IDs. FAISS saves vectors using those
exact IDs, then PostgreSQL commits. Deletion commits PostgreSQL first. Both orders can
leave orphan vectors after a crash, but cannot leave committed chunks without vectors
during ordinary process interruption. Startup removes orphans and refuses missing vectors.
Readers and writers share a lock; a filesystem lock rejects a second API worker.

**Manual check:** Run `pytest tests/test_vector_store.py`. Upload a document and restart
only the backend (`docker compose restart backend`); search again. Delete the document,
restart again, and verify that it cannot be retrieved. Inspect chunk IDs in PostgreSQL
with `docker compose exec db psql -U rag -d rag -c 'SELECT id, document_id FROM chunks;'`.

**Before moving on:** FAISS is not the metadata database. A flush assigns IDs but does
not commit. Two storage systems cannot share a normal SQL transaction; write order,
atomic file replacement, reconciliation, and paired backups matter.

## 7 — Raw semantic search

**Implemented:** Typed search contracts, query embedding, exact scoped top-k, metadata
lookup, and raw cosine scores/text. No LLM is called in this path.

**Files:** `backend/app/schemas.py`, `backend/app/retrieval.py`,
`backend/tests/test_retrieval.py`.

**How it works:** The database identifies eligible chunk IDs. FAISS ranks vectors;
only eligible IDs survive, then the first top-k are returned. This avoids the common
bug of selecting a global top-k and only then filtering documents, losing valid matches.
For this small teaching app FAISS ranks all vectors; this is intentionally not a large-scale design.

**Manual check:** POST `{"query":"When does inspection happen?","document_ids":[1]}` to
`/api/search`. Inspect scores, text, IDs and source ranges. Omit `document_ids` for all
documents; send `[]` for none. Compare results for paraphrases of the same question.

**Before moving on:** Cosine similarity ranges roughly from -1 to 1 and is not confidence.
Nearest passages can still be irrelevant. Retrieval failure and generation failure are different.

## 8 — Prompt and LLM

**Implemented:** Explicit context serialization, grounding instructions, prompt-injection
boundary, direct OpenAI Responses call, and structured answer/source-ID output.

**Files:** `backend/app/prompts.py`, `backend/app/llm.py`.

**How it works:** JSON contains the question and retrieved passage IDs/text. Separate
instructions tell the model to use only those passages and return a fixed not-found answer
when unsupported. A strict schema returns text plus IDs, never citation metadata.
Responses storage is disabled with `store=False`; this is not a guarantee of zero provider retention.

**Manual check:** With a key configured, POST `{"question":"When is inspection required?"}`
to `/api/chat/query`. Ask an unrelated question and check for the not-found answer.
Compare `/api/search` first if the response is surprising. Observe prompt and LLM steps in logs.

**Before moving on:** RAG supplies context at request time; it does not train the model.
Prompt instructions reduce hallucinations but cannot prove factual correctness or fully prevent injection.

## 9 — Citations and complete API

**Implemented:** Supporting-ID validation, deduplication, metadata-derived citations,
application-added answer labels, no-context fallback, all six routes, consistent errors,
and an upload request-body limit that also handles chunked transfer.

**Files:** `backend/app/{citations,chat,api,main,middleware}.py`,
`backend/tests/test_citations.py`, `backend/tests/test_api.py`, `backend/tests/test_llm.py`.

**How it works:** The model can select only IDs from retrieved context. Unknown IDs fail
closed. The app reads filename/location/excerpt from those chunks and creates `[1]` labels.
The labels apply to the answer as a whole, not individual sentences. No context or no
supporting IDs returns the fixed not-found response without invented citations.

**Manual check:** Upload the sample, ask about inspection, and compare the returned
excerpt and line range with the file. Try missing document IDs, whitespace-only questions,
and an oversized upload. Run `pytest` for an offline upload/search/chat/delete/restart flow.

**Before moving on:** A valid source ID proves provenance, not that the answer is entailed.
Read the excerpt to verify the model's claim. Citation metadata belongs to the application.

## 10 — Minimal learning UI

**Implemented:** Document upload/list/delete, explicit selection, independent questions,
answer history, expandable citations, and a raw retrieval inspection mode.

**Files:** `frontend/app/page.tsx`, `frontend/app/globals.css`,
`frontend/app/layout.tsx`, `frontend/app/api/[...path]/route.ts`.

**How it works:** React calls a same-origin Next.js proxy, which streams requests to FastAPI.
Only the backend holds the OpenAI key. The UI sends an explicit document-ID list, so
clearing selection can never accidentally search all documents. State shows real loading,
empty, success, and error conditions without pretending to stream pipeline progress.

**Manual check:** Open `http://localhost:3000`, upload `samples/permit.txt`, select it,
ask when inspection is needed, expand the source, and switch to **Inspect retrieval**.
Delete the file and verify it disappears from selection. Test a narrow mobile viewport
and keyboard navigation. Run `npm run typecheck` and `npm run build` in `frontend`.

**Before extending:** React state is ephemeral; refreshing clears question history.
Each question is independent, even though previous answers remain visible. Source text
is rendered as plain text, so document content cannot execute as HTML.
