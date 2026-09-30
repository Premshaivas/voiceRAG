# VoiceRAG

VoiceRAG turns recordings and video into searchable transcripts. Upload audio or video, import a supported video URL such as YouTube, transcribe it with AssemblyAI, and ask questions grounded in the transcript with timestamped source citations.

## Features

- Audio and video upload, plus video URL import through `yt-dlp` and FFmpeg.
- AssemblyAI transcription, transcript search, and timestamp-aware playback.
- Retrieval-augmented question answering with source citations and a safe transcript-excerpt fallback when the selected language model is unavailable.
- Configurable AssemblyAI LLM Gateway or OpenAI-compatible LLM provider.
- User authentication, owner-scoped documents, workspaces, and live voice-agent sessions.
- Background transcription with Celery and Redis; PostgreSQL metadata; Qdrant vector search; MinIO object storage; and ClamAV scanning.
- Labeled RAG evaluations, administration endpoints, and Prometheus metrics.

## Quick start with Docker

Prerequisites: Docker Desktop (or Docker Engine) with Docker Compose, and an AssemblyAI API key.

In PowerShell, from this directory:

```powershell
Copy-Item .env.example .env
```

Edit `.env` before starting the app. Set `ASSEMBLYAI_API_KEY`, replace `SECRET_KEY` with a long random value, set `ADMIN_EMAIL` to the account that should administer the app, and use `DOMAIN=localhost` for local development.

Start the stack:

```powershell
docker compose up --build
```

The first API start downloads the `all-MiniLM-L6-v2` embedding model. The Compose configuration keeps its cache in the ignored local `data/hf-cache-copy` directory so later container starts can reuse it.

Open the frontend at <http://localhost:5173>. The API listens at <http://localhost:8000>; `GET /health/ready` reports readiness. Register through the app before using protected document and answer endpoints. Compose also starts PostgreSQL, Redis, Qdrant, MinIO, ClamAV, the transcription worker, Celery beat, and Caddy.

Stop the stack with `docker compose down`. Compose volumes keep database, vector, object-storage, and Caddy data unless you explicitly remove volumes.

## Configure question answering

The default provider is AssemblyAI:

```dotenv
LLM_PROVIDER=assemblyai
LLM_GATEWAY_MODEL=claude-sonnet-4-6
```

The AssemblyAI account must have access to the selected LLM Gateway model. Transcription can still work without Gateway access; in that case, question and summary features fall back to transcript excerpts or heuristic summaries and indicate that generated LLM output is unavailable.

To use an OpenAI-compatible provider, set its credentials and model in the local `.env`:

```dotenv
LLM_PROVIDER=openai_compatible
LLM_API_KEY=your_provider_api_key
LLM_API_BASE_URL=https://api.openai.com/v1
LLM_API_MODEL=gpt-4o-mini
```

For another compatible service, set `LLM_API_BASE_URL` and `LLM_API_MODEL` to that provider's documented values. Keep real keys in `.env`; never commit `.env` or paste API keys into source files. The repository's `.env.example` contains placeholders only.

## Upload and ask

The main video features are available in the **Video Intelligence** panel:

1. Upload a video file or submit a video URL that `yt-dlp` can access.
2. VoiceRAG extracts audio, transcribes it, and indexes the transcript.
3. Review the transcript and key points, then ask questions about the video.
4. Follow citations to the relevant transcript excerpts and timestamps.

The principal video endpoints are `POST /api/video/upload`, `POST /api/video/import`, `GET` or `POST /api/documents/{document_id}/key-points`, and `POST /api/documents/{document_id}/ask`. URL importing requires outbound network access and only works for links the downloader can access; private or restricted videos may fail.

For audio and document workflows, `POST /api/documents/upload` is a synchronous upload path. Large uploads can use the multipart flow: `POST /api/uploads/initiate`, `GET /api/uploads/{upload_id}/parts`, and `POST /api/uploads/{upload_id}/complete`. The worker then processes the uploaded object in the background.

## API overview

| Area | Routes |
| --- | --- |
| Readiness | `GET /health`, `GET /health/ready` |
| Authentication | `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout` |
| Documents and answers | `GET /api/documents`, `POST /api/documents/upload`, `POST /api/answers` |
| Video | `POST /api/video/upload`, `POST /api/video/import`, `/api/documents/{id}/key-points`, `/api/documents/{id}/ask` |
| Transcript | `/api/documents/{id}/transcript`, `/api/documents/{id}/transcript/search` |
| Workspaces and voice history | `/api/workspaces`, `/api/voice-conversations` |
| RAG evaluation | `/api/evaluations/datasets`, `/api/evaluations/datasets/{id}/cases`, `/api/evaluations/datasets/{id}/run` |
| Administration | `/api/admin/users`, `/api/admin/audit`, `/api/admin/usage` |
| Metrics | `GET /metrics` |

Authentication is enabled by default in the production Compose setup. Access tokens are short-lived; refresh tokens use HttpOnly cookies with rotation and CSRF validation. Document and retrieval access is scoped to the current user. API documentation routes are disabled in the production app configuration.

## Local development

Python 3.11 is required for the backend. From this directory, create and activate a virtual environment, install the pinned dependencies, and configure `.env`:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

The backend needs PostgreSQL, Redis, Qdrant, MinIO, and ClamAV. Docker Compose is the simplest way to provide them. To work on the frontend separately:

```powershell
Set-Location frontend
npm install
npm run dev
```

Vite serves the development frontend on port 5173. The production frontend is built into an Nginx image that forwards API and WebSocket traffic to the API service.

## Tests and validation

From the project root:

```powershell
python -m pytest -q
docker compose config -q
Set-Location frontend
npm run build
```

The Python suite uses test doubles for external transcription, storage, embedding, and answer services. For live service checks, `scripts/integration_probe.py` can check API readiness, PostgreSQL, Redis, Qdrant, MinIO, AssemblyAI credentials, and—when requested—the configured LLM provider. A live LLM probe makes a small provider request and can incur provider usage.

## Configuration and deployment notes

- `.env.example` documents the supported environment variables. `scripts/validate_env.py` checks production settings.
- Production Compose selects Qdrant as the shared vector backend. Local application defaults can use Chroma for isolated development.
- Set a real public `DOMAIN` and strong unique credentials before deploying Caddy or exposing the stack publicly. Replace the development MinIO credentials as well.
- The API and worker containers run as a non-root user. Compose binds infrastructure ports to localhost and gates API startup on its required services.
- See [`DEPLOYMENT.md`](DEPLOYMENT.md) for backups, deployment, environment validation, and operational checks.

## Contributing

Keep credentials and generated data out of commits. Make focused changes, add or update tests for behavior changes, run the relevant backend and frontend checks above, and describe any required environment-variable changes in `.env.example` and this README.

## License

This project is available under the MIT License. See [`LICENSE`](LICENSE).
