# VoiceRAG Production Stack

This repository is the consolidated runnable baseline for the VoiceRAG project. It implements the core workflow and the first production-hardening layer: upload an audio file, transcribe it with AssemblyAI, index the transcript in ChromaDB, and answer questions through AssemblyAI's LLM Gateway with validated citations.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `ASSEMBLYAI_API_KEY` in `.env`. For the local service stack, start Docker Compose:

```bash
docker compose up --build
```

The Compose stack waits for PostgreSQL, runs Alembic migrations, starts Redis, Qdrant, MinIO, ClamAV, the API, a transcription worker, and the Celery beat process that relays outbox events. The production Compose profile explicitly selects Qdrant as the shared vector backend.

## Core API

The synchronous development endpoint remains available at `POST /api/documents/upload`. It is useful for local smoke tests but should not be used for multi-gigabyte files.

The hardened flow is:

1. `POST /api/uploads/initiate` creates a database record and an S3-compatible multipart upload.
2. `GET /api/uploads/{id}/parts?start=1&count=10` returns presigned part URLs.
3. The browser uploads each part directly to MinIO, S3, or R2 and records each ETag.
4. `POST /api/uploads/{id}/complete` completes the object, creates a pending document and job, and inserts an outbox event in the same transaction.
5. Celery beat relays the event. The worker downloads the object, runs `ffprobe`, scans it with ClamAV, transcribes it with AssemblyAI, indexes it, and marks the document completed.
6. `POST /api/answers` retrieves transcript chunks and returns an answer with validated `[S1]` citations.

Authentication endpoints are available at `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, and `/api/auth/logout`. Access tokens are short-lived. Refresh tokens are HttpOnly cookies, rotated on every refresh, and revoked as a family when reuse is detected. Refresh and logout require the CSRF header.

## Migrations and tests

Run migrations manually with `alembic upgrade head`. Run the automated tests with:

```bash
pytest -q
```

The test suite uses fake AssemblyAI, storage, embedding, and answer components, so it does not require external credentials or network access.

## Remaining limitations

The local development default remains Chroma. Production Compose uses persistent Qdrant so API and worker processes share one vector collection. ClamAV, MinIO, Qdrant, Redis, and PostgreSQL must be reachable from their dependent services. Docker itself was not available in the validation sandbox, so the Compose boot path and a real AssemblyAI Voice Agent session still need to be exercised on a machine with Docker and valid external credentials.

## Frontend

The first frontend phase is in `frontend/`. It provides registration and login, an in-memory access-token session, refresh retry de-duplication, direct multipart uploads with progress, a document library, and a grounded question panel that displays source excerpts.

Run it locally with:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` requests to the local FastAPI service. The frontend production build is verified with `npm run build`. A small Nginx production image is included in `frontend/Dockerfile`; it expects the API service to be reachable as `api:8000`.

## Authentication and ownership

Set `AUTH_REQUIRED=true` outside local development. With enforcement enabled, document listing, uploads, multipart URL issuance, multipart completion, and answers require a bearer access token. Documents and multipart sessions carry `owner_id`. A user sees only their own documents, and an answer request for another user's document returns `404` rather than leaking its existence. Vector metadata also carries the owner ID so owner-filtered retrieval can be applied by the RAG layer.

Passwords use direct bcrypt with a SHA-256 prehash to avoid bcrypt's 72-byte input limit without truncating user passwords. The refresh-token cookie remains HttpOnly and rotated, with CSRF validation and family reuse detection.

## Live Voice Agent

The live voice phase is implemented at `WS /api/voice-agent`. The backend bridge opens `wss://agents.assemblyai.com/v1/ws` with the permanent AssemblyAI key kept server-side. The browser never receives that key. It sends microphone audio to the bridge as base64 PCM16, receives base64 PCM16 reply audio, and renders live user/agent transcript events.

The bridge configures an inline Voice Agent with the `search_lecture` function tool. Tool calls search only the connected user's owned vector metadata. Tool results are held until the latest server event is `reply.done`, matching AssemblyAI's required client-side tool timing rule. The session is ended with `session.end` so the upstream session does not remain resumable and billable.

For Docker, the frontend is available at `http://localhost:5173`, with Nginx forwarding both HTTP and WebSocket `/api` traffic to the API container. Browser microphone permissions are required. The live agent requires `ASSEMBLYAI_API_KEY` and an account with Voice Agent access.

## Labeled RAG evaluation

The evaluation subsystem is available under `/api/evaluations`. Create a dataset, add cases with an expected answer and expected document IDs, then run the dataset against the current retrieval and grounded-answer pipeline.

```bash
DATASET=$(curl -s -X POST http://localhost:8000/api/evaluations/datasets \
  -H 'Content-Type: application/json' \
  -d '{"name":"Operating Systems smoke set"}' | jq -r .id)

curl -X POST "http://localhost:8000/api/evaluations/datasets/$DATASET/cases" \
  -H 'Content-Type: application/json' \
  -d '{"question":"What causes deadlock?","expected_answer":"Mutual exclusion and hold-and-wait.","expected_document_ids":["DOCUMENT_ID"]}'

curl -X POST "http://localhost:8000/api/evaluations/datasets/$DATASET/run"
```

Each run reports **retrieval recall**, **citation precision**, **citation recall**, token-overlap **answer F1**, and mean **latency in milliseconds**. Individual case results are available from `GET /api/evaluations/runs/{run_id}`. Evaluation datasets and runs follow the same owner isolation rules as documents. The schema is introduced by Alembic migration `0002_evaluations`.

## Evaluation dashboard

The workspace now includes a **05 / EVALUATE** panel. Create a labeled dataset, add questions with expected answers and document IDs, run the evaluation, and inspect metric cards plus per-case outputs. This is a thin authenticated client over `/api/evaluations`; it does not expose another data store or bypass owner isolation.

## Shared vector backend and production hardening

Set `VECTOR_BACKEND=qdrant` and `QDRANT_URL` for multi-worker deployments. The RAG adapter creates the configured collection if it does not exist, stores the original chunk ID and transcript text as payload fields, and translates owner/document filters into Qdrant filters. Chroma remains available for isolated development and test doubles.

The API and worker image now runs as a non-root `app` user. Compose binds infrastructure ports to localhost, persists Qdrant data in a named volume, gates API startup on database/Redis/Qdrant/object-storage readiness, enables `AUTH_REQUIRED=true` for the production API, and exposes API/frontend health checks.

## Deployment validation

The repository includes [`DEPLOYMENT.md`](DEPLOYMENT.md), `scripts/validate_env.py`, `scripts/smoke_stack.sh`, and `scripts/integration_probe.py`. These validate production configuration, build and boot the Docker Compose stack, wait for `/health/ready`, and probe PostgreSQL, Redis, Qdrant, MinIO, AssemblyAI, and optionally the LLM Gateway. The live probes require real credentials and reachable services; this sandbox does not have Docker or provider credentials, so they must be run on the deployment host.

The deployment stack includes Caddy for HTTPS, automatic certificate renewal, security headers, and reverse proxying to the frontend. Set `DOMAIN` to a public DNS name before deployment. Timestamp citation playback now uses HTTP range responses for local files and short-lived presigned GET URLs for object-storage files.

## Grounding quality safeguards

Answers now discard retrieval results whose cosine distance exceeds `RETRIEVAL_MAX_DISTANCE` and refuse before making an LLM request when no sufficiently relevant evidence remains. A generated answer must cite enough of its factual sentences to satisfy `MIN_CITATION_COVERAGE`; otherwise it is converted to the safe refusal response. Successful answers include confidence and citation-coverage values, which the frontend displays beside the response. The defaults are `0.72` for maximum retrieval distance and `0.75` for minimum citation coverage.

## Remaining product areas implemented

The workspace now includes a transcript viewer/search panel backed by owner-scoped `/api/documents/{document_id}/transcript` endpoints. Voice sessions retain recent browser history and retry transient WebSocket disconnects twice. Administrators can be bootstrapped with `ADMIN_EMAIL`, manage user roles, delete documents, inspect audit events, and view usage totals through `/api/admin`. Request logs and Prometheus-compatible counters are available at `/metrics`. CI is defined in `.github/workflows/ci.yml` for backend tests, frontend builds, Compose validation, and Docker image builds.

## Timestamped audio citations

AssemblyAI word-level timestamps are now preserved during indexing. Retrieved sources include `start_ms` and `end_ms` metadata when available. The answer panel exposes a **Play from Ns** control that fetches the owner-protected audio file and starts playback at the cited timestamp. Local uploads stream from their retained file; multipart uploads are downloaded from S3-compatible storage on demand and cleaned up after the response.

## Performance pass

The API now uses GZip compression for larger responses. Repeated owner-scoped answers are served from a bounded TTL cache, repeated query embeddings use an LRU-style TTL cache, and evaluation cases run with bounded concurrency. Tune `ANSWER_CACHE_TTL_SECONDS`, `ANSWER_CACHE_MAX_ENTRIES`, `QUERY_EMBEDDING_CACHE_MAX_ENTRIES`, and `EVALUATION_CONCURRENCY` in the environment. Caches include owner and document scope in their keys; they do not cross authorization boundaries.


## Final hardening pass

The final pass adds persisted AssemblyAI word metadata for speaker-aware transcript rendering and synchronized word highlighting, persisted voice conversations/messages, user-owned workspaces, optional OpenTelemetry spans, Prometheus/Grafana services under the `observability` profile, `scripts/backup.sh`, `scripts/deploy.sh`, dependency/container security scanning, and a manually triggered provider integration workflow in `.github/workflows/integration.yml`.
