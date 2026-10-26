# RAG Learning Lab

A small document-question-answering application built to make retrieval-augmented
generation (RAG) understandable. Upload a text-based PDF, DOCX, or UTF-8 TXT, inspect
semantic search results, then ask for an answer backed by expandable source citations.

The stack is Next.js + React + TypeScript, FastAPI + SQLAlchemy + PostgreSQL,
OpenAI embeddings + OpenAI Responses, FAISS, PyMuPDF, python-docx, and Docker Compose.
There is no LangChain, LlamaIndex, or hidden retrieval framework.

Start with the [ten milestone walkthroughs](docs/milestones.md). Each records what was
implemented, the files involved, how it works, a manual check, and concepts to learn next.

**Running without Docker or debugging in PyCharm?** Follow the
[local PyCharm setup](docs/pycharm.md). The saved **RAG Backend (local)** configuration
starts the backend directly using the project's `.venv` and local PostgreSQL.

**Test with Postman:** import
[`postman/RAG-Learning-Lab.postman_collection.json`](postman/RAG-Learning-Lab.postman_collection.json).
It includes all six API routes and uses `http://127.0.0.1:8000` by default, with no
separate environment required. In the upload request, choose your file under
**Body → form-data → file**. A successful upload saves `document_id` automatically.
Search and Chat default to all documents; use `"document_ids": [{{document_id}}]`
to limit them to the uploaded document. Delete is optional cleanup: deselect it in
Collection Runner if you want to keep your upload. OpenAI credentials belong in
the backend `.env`; restart the backend after setting them.

## Quick start with Docker

Requirements: Docker with Compose, and an OpenAI API key with access to the configured
embedding and LLM models. Docker Desktop is sufficient on macOS/Windows.

```sh
# Only if .env does not already exist:
cp .env.example .env
# Edit .env and set OPENAI_API_KEY. Keep the key out of source control.
docker compose up --build
```

Open the [application](http://localhost:3000), [interactive API docs](http://localhost:8000/docs),
or [health endpoint](http://localhost:8000/health).

1. Upload `samples/permit.txt`.
2. Keep it selected and ask: **When does inspection need to happen?**
3. Expand the source and compare the excerpt and line numbers to the file.
4. Switch to **Inspect retrieval** and ask the same question. This calls `/api/search`
   and shows passages and cosine scores without using the LLM.
5. Ask **What is the inspector's phone number?** The sample does not contain that answer.

Without an API key, the app still starts and you can list/delete existing documents.
New ingestion and semantic queries need embeddings and will return a friendly 503 error.
A query against no selected documents returns an empty result or a not-found answer.

Only loopback ports are published. This is a local learning app with no authentication;
do not expose it publicly as-is. Uploaded text and questions are sent to OpenAI.
Original uploaded files are not retained; extracted chunks, their metadata, and vectors are.

```sh
docker compose logs -f backend
docker compose down  # stops services but preserves the two named data volumes
```

Do not delete either data volume independently. PostgreSQL and FAISS must stay together.
`docker compose down -v` deletes **all uploaded metadata and vectors** and is only for an
intentional reset. Stop the backend before taking paired volume backups.

## Local development

Use Python 3.12 or 3.13, Node.js 22+, and a running PostgreSQL 17 instance. The repository
contains pinned direct Python dependencies and an npm lockfile.
Create the PostgreSQL database with UTF-8 encoding (not SQL_ASCII).

```sh
# Only if .env does not already exist:
cp .env.example .env
# Set OPENAI_API_KEY and DATABASE_URL for your local PostgreSQL.
# On macOS with Homebrew, if PostgreSQL is not already running:
brew services start postgresql@17
# Create the local role/database once using the steps in docs/pycharm.md.

python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --loop asyncio
```

Run the Python command from the repository root so `.env` and `data/faiss` resolve
there. On Windows, venv executables live under `.venv/Scripts`; use Docker for the
backend because the current single-process file lock uses Unix `fcntl`.

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

The Next.js server proxies `/api/*` to `http://127.0.0.1:8000`. For a different backend,
set `API_INTERNAL_URL` in the frontend process environment. Compose sets it to
`http://backend:8000`. The OpenAI key is never a `NEXT_PUBLIC_*` variable and is never
sent to the browser. Health and Swagger are accessed directly on port 8000.

Run exactly **one backend worker**, with one FAISS directory per database. A file lock
rejects a second writer. Stop the old process before restarting; avoid multiple reload
processes sharing the index.

## What RAG does

An LLM alone does not know your uploaded documents. RAG first finds likely relevant
passages and places them in the model's input. The model then answers from that context.
This is retrieval at inference time, not model training or fine-tuning.

There are two independent flows:

```text
INGESTION
Upload → validate → extract → normalize → chunk → embed
                                                    ↓
                                 PostgreSQL assigns chunk IDs
                                                    ↓
                                 FAISS stores ID + vector on disk
                                                    ↓
                                 PostgreSQL commits text + metadata

QUESTION
Question → embed → FAISS similarity search → eligible chunk IDs
                                                    ↓
                                   PostgreSQL passage + metadata lookup
                                         ↙                       ↘
                           /api/search returns               construct prompt
                           passages and scores                     ↓
                                                            OpenAI LLM
                                                                  ↓
                                                   validate supporting chunk IDs
                                                                  ↓
                                               answer + app-generated citations
```

The frontend does not perform extraction, retrieval, or prompt construction.
FastAPI routes only validate HTTP input and delegate to explicit services.

## Code map

| Module | Responsibility |
| --- | --- |
| `backend/app/api.py` | Six HTTP endpoints and response models |
| `config.py`, `errors.py`, `schemas.py` | Configuration, friendly failures, typed contracts |
| `uploads.py`, `middleware.py` | Extension/MIME, byte limits, multipart envelope limits |
| `extraction.py` | PyMuPDF pages, Word paragraphs, UTF-8 lines |
| `normalization.py` | Normalize Unicode/whitespace while retaining source positions |
| `chunking.py` | Token windows, overlap, source-span mapping |
| `embeddings.py` | Typed embedding interface and direct OpenAI SDK adapter |
| `vector_store.py` | FAISS normalization, ID mapping, exact search, disk persistence |
| `database.py` | SQLAlchemy document/chunk models and session creation |
| `ingestion.py` | Explicit ingestion sequence and coordinated deletion |
| `retrieval.py` | Query embedding, scoped search, metadata hydration |
| `prompts.py` | Grounding rules and serialized context |
| `llm.py` | Direct Responses call with a structured output schema |
| `citations.py` | Validate supporting IDs and construct sources from stored metadata |
| `chat.py` | Retrieval → prompt → generation → citations |
| `main.py` | Startup, dependency wiring, index reconciliation, error translation |
| `backend/tests/` | Real parsers/FAISS with deterministic model doubles |
| `frontend/app/page.tsx` | Upload, library, selection, questions, answers, retrieval inspection |
| `frontend/app/api/[...path]/route.ts` | Same-origin streaming HTTP proxy |

Paths in the table after the first backend entry are relative to `backend/app`.
Read `ingestion.py`, then `retrieval.py`, then `chat.py` to follow the two flows.

## Extraction and source coordinates

- **PDF:** PyMuPDF extracts text per page; citations use the original one-based page
  number. Chunks never cross a page boundary. Image-only/empty PDFs and password-protected
  PDFs are rejected. A mixed PDF contributes only its extractable text; there is no OCR.
- **DOCX:** python-docx reads body paragraphs, including table-cell paragraphs, in XML
  order. Paragraph numbers are one-based and count blank paragraphs too. Ranges are
  stable within the uploaded document, but are not Word page numbers or a visible ruler.
  Headers, footers, comments, footnotes, and embedded images are not indexed.
- **TXT:** UTF-8 (optionally BOM) is required. Citations use original one-based line
  ranges, counting blank lines. Other encodings and NUL-containing binary data are rejected.

Normalization cleans Unicode and repeated horizontal whitespace. It does not renumber
units. Original bytes are not stored; excerpts show normalized text.

## Tokens, chunks, and overlap

A token is a model text unit: sometimes a word, sometimes part of a word or punctuation.
`tiktoken`'s `cl100k_base` tokenizer defines the windows. The default is approximately
700 tokens per chunk, with 120 tokens repeated into the next chunk. A 700-token window
therefore normally advances 580 tokens. PDF page boundaries can create smaller chunks.

Small chunks can lose context; large chunks can dilute the relevant passage. Overlap
helps preserve information around boundaries but increases embedding costs and duplicates
some retrieved evidence. Character offsets prevent broken Unicode at token boundaries;
a few scripts can slightly exceed the nominal token budget. Chunk settings affect new
uploads only; re-upload a document to compare settings.

## Embeddings, similarity, and FAISS

An embedding is a fixed-length numeric vector representing text. This app defaults to
`text-embedding-3-small` with 1536 dimensions. It uses the same model and dimensions for
both chunks and questions. The adapter batches calls, restores response order, and
validates vector shape and values.

FAISS stores float32 vectors in `IndexFlatIP`, wrapped by `IndexIDMap2`. We L2-normalize
vectors first, so an inner product is cosine similarity. The score is roughly -1 to 1;
**it is not a probability or confidence score**. Search always finds nearest eligible
neighbors, even if all of them are irrelevant. There is no universal relevance threshold.

`Flat` search is exact and scans the index. For clarity, scoped search ranks all vectors,
filters against eligible database chunk IDs, then takes top-k. Filtering only after taking
a global top-k would incorrectly miss matches in selected documents. This simple
implementation is appropriate for a small local corpus, not millions of chunks.

## Metadata mapping and consistency

PostgreSQL stores `documents` and `chunks`; the latter contains text, token count, document
ID, and page/paragraph/line fields. `Chunk.id` is also the FAISS vector ID.

The two stores do not share a transaction:

1. Ingestion computes embeddings before opening its write transaction.
2. SQLAlchemy `flush()` reserves chunk IDs without committing metadata.
3. FAISS writes a new snapshot to a temporary file, fsyncs it, then atomically replaces
   the previous index. Only then does it publish the new in-memory index.
4. PostgreSQL commits. Interrupted writes can leave orphan vectors, but queries always
   require a corresponding database row.
5. Deletion commits metadata removal first, then removes vectors. A failed vector cleanup
   leaves ignored orphans that startup removes.
6. Startup loads the disk index and compares its IDs with the database. Orphans are removed;
   missing vectors cause a startup error instead of silently returning incomplete results.

A thread lock serializes queries and storage mutations. A process lock enforces one API
worker. Snapshot replacement protects ordinary process interruption, not every power-loss,
filesystem failure, or independent backup/restore scenario. Back up both stores together.

`embedding.json` records model and dimension settings. Changing either requires a fresh
paired store and re-ingestion; mixing incompatible embedding spaces is rejected.
Schema creation uses `create_all` for this initial version; it does not migrate existing tables.

## Prompt construction, answers, and citations

`prompts.py` serializes the question and retrieved passage IDs/text. Separate instructions
require the model to use only this context and ignore instructions inside documents.
If the answer is absent, the response is:

> The answer was not found in the uploaded documents.

The LLM returns structured `answer` and `source_ids`. It cannot supply citation metadata.
The app validates IDs against the retrieved set, removes duplicates, copies filename,
location and excerpt from database results, and appends `[1]`, `[2]`, etc. to the answer.
These are answer-level citations, not independently verified sentence-level entailment.
An unknown source ID returns an error rather than an invented citation. No supporting IDs
or no retrieved context produces the fixed not-found answer. Empty retrieval skips the LLM.

Prompt injection and hallucinations remain possible: a valid source ID does not prove the
answer faithfully follows that source. Always inspect the excerpts. The UI renders plain
text, never HTML from uploads or the model. Each question is independent; displayed history
is in browser memory only and is not sent back as conversation context.

## Configuration

Use `.env` at the repository root. Restart the backend after changes.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL on localhost | SQLAlchemy URL; Compose overrides the host to `db` |
| `OPENAI_API_KEY` | empty | Required for paid embedding/generation calls |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Uses the dimensions-capable embedding API |
| `EMBEDDING_DIMENSIONS` | `1536` | Must match the model and persisted index |
| `LLM_MODEL` | `gpt-4.1-mini` | Must support Responses and JSON-schema structured output |
| `CHUNK_SIZE` | `700` | Approximate token window, 2–8000 |
| `CHUNK_OVERLAP` | `120` | Must be nonnegative and smaller than chunk size |
| `RETRIEVAL_TOP_K` | `5` | Default number of retrieved chunks, 1–20 |
| `MAX_UPLOAD_MB` | `20` | File limit in MiB; 1–100 |
| `MAX_EXTRACTED_CHARS` | `2000000` | Text budget; DOCX expansion is separately bounded |
| `FAISS_DIRECTORY` | `./data/faiss` | Index, model fingerprint, and process lock |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | JSON list for direct browser API access |

`POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` configure the Compose database.
The example password is only for local development. Keep the connection URL consistent
when changing credentials; URL-encode reserved password characters. Existing PostgreSQL
volumes retain their original database credentials even if Compose environment values change.

## API examples

Run these from the repository root. Replace document IDs with those returned by your upload.

```sh
curl http://localhost:8000/health

curl -F 'file=@samples/permit.txt;type=text/plain' \
  http://localhost:8000/api/documents/upload

curl http://localhost:8000/api/documents

curl -X POST http://localhost:8000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"When does inspection happen?","document_ids":[1],"top_k":5}'

curl -X POST http://localhost:8000/api/chat/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Does the permit require inspection?","document_ids":[1]}'

curl -X DELETE http://localhost:8000/api/documents/1
```

For PDFs use MIME `application/pdf`; for DOCX use
`application/vnd.openxmlformats-officedocument.wordprocessingml.document`.
Extension and declared MIME must agree, and the parser must successfully read the contents.

`document_ids` omitted or `null` searches all documents; `[]` searches none.
Unknown selected IDs return 404. Optional `top_k` overrides the configured default.
Queries are trimmed, must be nonempty, and have a 2000-character limit.

Search response (example score, not a measured result):

```json
{
  "query": "When does inspection happen?",
  "results": [{
    "chunk_id": 12,
    "document_id": 1,
    "text": "Inspection is required before occupancy.",
    "score": 0.91,
    "filename": "permit.pdf",
    "page": 4
  }]
}
```

Chat response:

```json
{
  "answer": "Inspection is required before occupancy. [1]",
  "sources": [{
    "citation": 1,
    "chunk_id": 12,
    "document_id": 1,
    "filename": "permit.pdf",
    "page": 4,
    "excerpt": "Inspection is required before occupancy.",
    "score": 0.91
  }]
}
```

DOCX sources have `paragraph_start`/`paragraph_end`; TXT sources have
`line_start`/`line_end`. Unused location fields are omitted.
Upload returns 201, deletion returns 204. Common failures are 400 (file contents/type),
413 (size limit), 422 (request fields), 404 (document), and 503 (model/storage dependency).
Errors use `{"error":{"code":"...","message":"..."}}`.

## Tests and verification

```sh
# From the repository root:
cd backend
../.venv/bin/pytest -q
../.venv/bin/ruff check app tests
../.venv/bin/ruff format --check app tests

cd ../frontend
npm run typecheck
npm run build
```

The default suite creates isolated SQLite databases and real FAISS indexes in temporary
directories. Tests generate actual PDF/DOCX bytes and cover text parsing, source positions,
chunk overlap, Unicode, the OpenAI adapter contracts, persistence/reload/delete, filtered
retrieval, citations, invalid uploads, body limits, API errors, and the complete API flow.
Only model calls are substituted, so no API key or paid requests are needed.

For PostgreSQL-backed API tests, supply a disposable database URL using
`TEST_DATABASE_URL` (see `backend/tests/test_api.py`). Each test creates and drops its own
unique schema. Other tests remain lightweight SQLite/unit checks. Never use a production
database for testing. Live OpenAI output quality requires an API key and manual validation.

```sh
# From backend; substitute your disposable PostgreSQL database URL:
TEST_DATABASE_URL='postgresql+psycopg://rag:rag_local_only@localhost:5432/rag' ../.venv/bin/pytest -q
```

See [the verification record](docs/verification.md) for checks actually performed and their limits.

Logs show upload, extraction, normalization, chunk count, embedding count, FAISS writes,
query embedding, search, retrieval count, prompt construction, and LLM completion.
Raw questions, document text, and API keys are not intentionally logged.

## Limitations and future work

This is a synchronous, single-worker learning implementation. Uploads wait for the whole
pipeline. Queries serialize around the shared index, including their embedding request.
Large corpora and concurrent users need a different storage/concurrency design.
There is no duplicate detection; uploading a file again creates another document.
FAISS snapshots copy the full index and can use significant memory/disk as the corpus grows.

PDF column/table reading order can be imperfect. DOCX layout and automatic list labels
are not reproduced. TXT requires UTF-8. There is no OCR, original-file download, or
multimodal processing. Citation correctness is limited to source provenance; the model
can still misread a passage or fail to abstain on an unrelated question.

Deliberately excluded from this version: authentication, OCR, images/audio/video,
LangChain/LlamaIndex, Celery, Redis, streaming, WebSockets, agents, hybrid search,
reranking, and S3. Possible later phases include those capabilities, explicit database
migrations, a reindex command, per-sentence citation validation, retrieval evaluation,
background processing, and stronger multi-user data isolation. None is required to
understand the pipeline in this version.

## Primary references

- [OpenAI embeddings guide](https://developers.openai.com/api/docs/guides/embeddings)
- [OpenAI text generation guide](https://developers.openai.com/api/docs/guides/text)
- [Next.js installation](https://nextjs.org/docs/app/getting-started/installation)
