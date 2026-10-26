# Verification record

Verified on 2026-10-21, using Python 3.13.5, Node 25.1.0, and PostgreSQL 17.7.

| Check | Result |
| --- | --- |
| Default Python suite | 42 passed |
| Suite with PostgreSQL-backed API integration tests | 42 passed; API tests use isolated schemas |
| Ruff lint | Passed |
| Ruff formatting | Passed |
| Next.js production build | Passed |
| TypeScript typecheck | Passed |
| Compose YAML parsing and local build-path/volume references | Passed |
| Real FastAPI startup with PostgreSQL and default OpenAI adapters | Passed |
| Health and missing-key error against the running backend | Passed |
| Upload through the Next.js proxy into real PostgreSQL/FAISS | Passed with model test doubles |
| Browser document selection, chat, source expansion, retrieval mode | Passed with model test doubles |
| Browser layout at desktop and 390px width | Checked visually; no layout overflow observed |

Backend coverage includes actual PDF/DOCX extraction, TXT line positions, overlap,
Unicode boundaries, embedding SDK contracts, FAISS insert/search/reload/delete, model
fingerprints, process locking, orphan reconciliation, disk-write failure, scoped retrieval,
invalid source IDs, no-context fallback, malformed requests, upload limits including
chunked transfer, and full upload/search/chat/delete/restart flows.

OpenAI calls were replaced only in tests and the temporary UI verification server.
The production app has no fake-embedding mode or canned answers. Test vectors do not
establish semantic retrieval quality. The fake UI server was stopped after verification.

Not executed:

- Docker image builds / `docker compose up`: Docker was not installed on this machine.
- Live OpenAI embeddings or generated answers: no `OPENAI_API_KEY` was configured.
- Browser file chooser upload: the Chrome extension disallowed local file access.
  The same upload endpoint and Next.js proxy were checked by HTTP instead.

The Python suite emitted upstream SWIG and Starlette/httpx deprecation warnings; no test
failures. Docker targets Python 3.12 and Node 22, so container-specific runtime behavior
still needs a Docker run. Temporary verification services and data were cleaned up.
