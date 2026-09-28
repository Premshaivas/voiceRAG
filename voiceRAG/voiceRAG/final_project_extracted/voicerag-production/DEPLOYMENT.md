# VoiceRAG deployment validation

## 1. Prepare production configuration

Copy the template and replace every placeholder before starting the stack:

```bash
cp .env.example .env
python3 scripts/validate_env.py
```

The validator requires a strong `SECRET_KEY`, an AssemblyAI API key, PostgreSQL, Redis, Qdrant, and S3-compatible storage URLs. Production authentication must remain enabled.

## 2. Run the Docker stack smoke test

On a Docker-enabled machine:

```bash
./scripts/smoke_stack.sh
```

The script validates the Compose file, builds all images, starts PostgreSQL, Redis, Qdrant, MinIO, ClamAV, migrations, API, workers, beat, and frontend, waits for `/health/ready`, and runs the integration probe. Containers are removed afterward unless `KEEP_STACK=1` is set.

## 3. Run live integration checks separately

With the stack running and `.env` loaded:

```bash
set -a; . ./.env; set +a
python3 scripts/integration_probe.py --api-url http://127.0.0.1:8000
```

This checks API health/readiness, TCP reachability for PostgreSQL and Redis, Qdrant collections, the MinIO bucket, and AssemblyAI credentials. Add `--check-llm` to make one minimal LLM Gateway request:

```bash
python3 scripts/integration_probe.py --api-url http://127.0.0.1:8000 --check-llm
```

The LLM check performs a real request and may consume provider quota. The scripts report skipped, failed, and passed checks explicitly; they never treat missing credentials as success.

## 4b. Operations and administration

Set `ADMIN_EMAIL` before registering the bootstrap administrator. The account receives the `admin` role and can use `/api/admin/users`, `/api/admin/users/{id}/role`, `/api/admin/documents/{id}`, `/api/admin/audit`, and `/api/admin/usage`. Keep `/metrics` behind the HTTPS proxy or an internal network policy; it exposes request counters and latency totals but no document contents.

Transcript viewing and search are available at `/api/documents/{id}/transcript` and `/api/documents/{id}/transcript/search?q=...`. The frontend exposes both in the transcript panel.

CI/CD is defined in `.github/workflows/ci.yml`. It runs backend tests and compilation, frontend type/build checks, Compose parsing, and both Docker image builds on every push and pull request.

## 5. Final operations

Use `scripts/deploy.sh` for a validated rebuild, migration, startup, and readiness check. Use `scripts/backup.sh` to create PostgreSQL, Qdrant snapshot, and object-storage backups with SHA-256 checksums. Start optional local dashboards with `docker compose --profile observability up -d prometheus grafana`; Prometheus scrapes `/metrics`. The API emits optional OpenTelemetry spans when an OpenTelemetry exporter is configured by the deployment.

Voice conversation records are available under `/api/voice-conversations`, and workspaces under `/api/workspaces`. The manually triggered `integration.yml` workflow runs provider checks only when the required GitHub secrets are present, so ordinary CI remains safe without production credentials.

## 5. HTTPS and domain setup

Set `DOMAIN` to a real DNS name pointed at the deployment host. The Compose stack includes Caddy on ports 80 and 443. Caddy obtains and renews a trusted certificate automatically when the domain resolves publicly and ports 80/443 are reachable. Certificate and Caddy state persist in named volumes.

Do not use `DOMAIN=localhost` for a public deployment. Replace the example S3 credentials and configure a firewall so only the HTTPS proxy is publicly reachable.

## 6. Efficient citation playback

The authenticated audio endpoint supports HTTP `Range` requests for local files and returns a short-lived presigned GET redirect for S3/MinIO objects. This lets browsers seek and stream large recordings without the API downloading the entire object into temporary storage.

## 4. Required external values

Use a long random `SECRET_KEY`. Set `ASSEMBLYAI_API_KEY` and confirm that the AssemblyAI account can access both transcription and the LLM Gateway. For hosted Qdrant and object storage, replace the local URLs, add `QDRANT_API_KEY` when required, and use non-default storage credentials.
