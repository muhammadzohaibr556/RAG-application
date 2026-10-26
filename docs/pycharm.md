# Run and debug locally in PyCharm (no Docker)

Docker is optional. For local development, Python connects directly to PostgreSQL
on your Mac, and FAISS writes to `data/faiss` in the project. Docker files remain
available for a later container-based setup.

## What caused the current error

The original PyCharm `rag` configuration ran:

```text
uvicorn backend.app.main:app --reload
```

The application's imports use `from app...`, so the directory containing `app`
(`backend`) must be on Python's import path. The saved **RAG Backend (local)**
configuration uses `app.main:app --app-dir backend` to make that explicit.
It also sets the project root as the working directory so `.env` and `data/faiss`
resolve consistently. No source-code import rewrite or Docker installation is needed.

## Setup on this Mac

The project virtual environment already has the dependencies installed. PostgreSQL 17
is running locally on port 5432. The `rag` login role, UTF-8 `rag` database, and root
`.env` were created during setup. You do not need to recreate them.

Verified in PyCharm Debug: `/health` returned 200 with `status: ok`, `/docs`
returned 200, and `/api/documents` returned an empty list. A health request paused
at `api.py:17`, Step Over advanced to line 18, and Resume completed the request.
The temporary verification breakpoint was removed. Live OpenAI calls were not
tested because no API key is configured.

The local connection in `.env` is:

```dotenv
DATABASE_URL=postgresql+psycopg://rag:rag_local_only@localhost:5432/rag
FAISS_DIRECTORY=./data/faiss
OPENAI_API_KEY=
```

Add your OpenAI API key to `.env` yourself when you want to embed documents or generate
answers, then restart the backend. The file is ignored by Git. A key is not needed to
start the server, inspect Swagger, check `/health`, or debug extraction/chunking tests.

## Run / Debug configuration

Open the **whole `RAG-application` folder** in PyCharm. Select **RAG Backend (local)**
from the run-configuration dropdown, then click **Debug** (the bug icon).
If it is not shown immediately, reopen the project to load `.run/*.run.xml`.

To create the same configuration manually, use **Run → Edit Configurations → + → Python**:

| Field | Value |
| --- | --- |
| Name | `RAG Backend (local)` |
| Python interpreter | `/Users/muhammadzohaib/Documents/RAG-application/.venv/bin/python` |
| Run target type | Module name |
| Module name | `uvicorn` |
| Parameters | `app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --loop asyncio` |
| Working directory | `/Users/muhammadzohaib/Documents/RAG-application` |
| Environment variables | `PYTHONUNBUFFERED=1` |

The application loads `.env` itself. You do not need an EnvFile plugin or a Docker
interpreter. The configuration is saved in `.run/RAG Backend (local).run.xml`.
Use this configuration instead of the original `rag` configuration.

Auto-reload is deliberately disabled: it launches a child process and complicates
breakpoints. `--loop asyncio` uses the standard Python event loop for debugging.
Restart the debug session manually after code changes. Run only one server at a time,
because one process must own the FAISS index.

Success looks like `Application startup complete` and
`Uvicorn running on http://127.0.0.1:8000` in the Debug console.

### PyCharm 2025.2 asyncio debugger compatibility

This installed PyCharm build (`252.28539.27`) patches `asyncio.run` in a way that
does not accept Uvicorn's `loop_factory` argument. This caused a second startup
error after fixing the import path. The following IDE setting was changed on this
Mac and the backend was then verified under the debugger:

1. Open **Help → Find Action**, search **Registry**, and open **Registry…**.
2. Type `python.debug.asyncio.repl` to filter the list.
3. Clear its checkbox, close the dialog, and restart the debug session.

This disables top-level `await` support in the debugger console. Normal application
asyncio execution and line breakpoints still work. It is an IDE-wide setting, so
other Python debug sessions in this PyCharm installation also use it. A run-config
environment variable alone did not work because this IDE overrides it. No package
downgrade or application-code patch is required.

- [Health](http://127.0.0.1:8000/health)
- [Swagger API docs](http://127.0.0.1:8000/docs)
- [Uploaded documents](http://127.0.0.1:8000/api/documents)

## Step through a request

1. Open `backend/app/api.py` and put a breakpoint on the first executable line inside
   `health` (the `with request.app.state.sessions()` line).
2. Start **RAG Backend (local)** with **Debug**.
3. Open `http://127.0.0.1:8000/health` in a browser. Starting the server alone does not
   execute endpoint code: you must send a request.
4. PyCharm pauses at the breakpoint. Inspect `request.app.state` in Variables.
   **Step Over** executes the current line; **Step Into** enters a called function;
   **Resume Program** continues the request. Use the Debug toolbar or
   **Run → Debugging Actions**; keyboard shortcuts depend on your keymap.
5. Resume so the browser receives the response. A request stays loading while paused.

Useful next breakpoints:

| Learning step | Function |
| --- | --- |
| Startup and dependency wiring | `main.py`: `lifespan` |
| Upload orchestration | `ingestion.py`: `IngestionService.ingest` |
| File validation | `uploads.py`: `read_upload` |
| Extract and normalize | `extraction.py`: `extract`; `normalization.py`: `normalize` |
| Token windows | `chunking.py`: `chunk_units` |
| OpenAI embeddings | `embeddings.py`: `OpenAIEmbedder.embed` |
| FAISS persistence/search | `vector_store.py`: `FaissStore.add` / `search` |
| Query retrieval | `retrieval.py`: `RetrievalService.search` |
| Prompt and generation | `prompts.py`: `build_prompt`; `llm.py`: `answer` |
| Citation construction | `citations.py`: `build_citations` |

Use Swagger's **Try it out** to upload `samples/permit.txt` or submit search/chat JSON.
Without a key, an upload can reach extraction and chunking, then returns a friendly 503
at the embedding stage. For the whole pipeline without paid calls, debug
`backend/tests/test_api.py::test_full_pipeline_and_restart`: right-click the test function
and select **Debug pytest…**. Tests inject deterministic model doubles, so their scores
and answers demonstrate plumbing rather than semantic quality. The tests use temporary
databases/indexes and do not modify the local app's data.

## Start from a terminal instead

From the project root:

```sh
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --loop asyncio
```

Stop this terminal server before using PyCharm Debug. To also run the frontend, open
a separate terminal, run `cd frontend`, then `npm run dev`, and open
`http://localhost:3000`. The frontend is optional when using Swagger to debug the backend.

## Reproduce setup on another Mac

Install Python 3.12/3.13 and PostgreSQL 17 if absent. With Homebrew:

```sh
brew install postgresql@17
brew services start postgresql@17
export PATH="$(brew --prefix postgresql@17)/bin:$PATH"
pg_isready
```

Create a local development role and database **once**, using your local PostgreSQL
administrator account. If they already exist, use them instead of recreating them:

```sh
psql -d postgres -c "CREATE ROLE rag LOGIN PASSWORD 'rag_local_only' NOSUPERUSER NOCREATEDB NOCREATEROLE;"
createdb --owner=rag --encoding=UTF8 --template=template0 rag
```

Then, from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
# Only when .env does not already exist:
cp .env.example .env
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `No module named 'app'` | Use module `uvicorn`, target `app.main:app`, and `--app-dir backend`; working directory must be the project root. |
| `No module named 'uvicorn'` | Choose the project's `.venv/bin/python`, then install requirements into that interpreter. |
| `_patch_asyncio... unexpected keyword argument 'loop_factory'` | Disable `python.debug.asyncio.repl` in PyCharm Registry as described above, then restart Debug. |
| Connection refused on 5432 | Check `pg_isready`; start your local PostgreSQL service. |
| Role/database `rag` does not exist | Complete the one-time PostgreSQL setup above. |
| Password authentication failed | Make `.env` match your PostgreSQL login credentials. |
| `could not translate host name "db"` | `db` is Compose DNS; local `DATABASE_URL` must use `localhost`. |
| Address already in use on 8000 | Stop the previous server/debug session; do not start two copies. |
| FAISS reports another worker | Stop the old backend process; deleting `writer.lock` is not a fix. |
| Key is configured but app cannot see it | Verify root working directory and restart; process environment variables override `.env`. |
| Breakpoint does not pause | Launch with Debug, send a request to that route, and make sure breakpoints are enabled. |
| Browser appears stuck | Check whether PyCharm paused at a breakpoint, then Resume. |

Reference: [JetBrains Python run/debug configuration documentation](https://www.jetbrains.com/help/pycharm/run-debug-configuration-python.html).
