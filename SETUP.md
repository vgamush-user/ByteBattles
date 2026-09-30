# ByteBattles — Setup Guide

ByteBattles has two runnable services (**api**, **judge**) plus three infra dependencies (**PostgreSQL**, **Redis**, **MinIO**). The judge also needs **Docker** available to it (it spawns sandbox containers), so running the judge itself inside Docker requires mounting the host's Docker socket — already wired up in `docker-compose.yaml`.

The easiest path is Docker Compose end-to-end. A manual/local path is included below for anyone iterating on judge or api code without rebuilding images every time.

## 0. Prerequisites

- Docker + Docker Compose
- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) (dependency manager used by this project — see `pyproject.toml` / `uv.lock`)

## 1. Environment file

```bash
cp .env.example .env
```

Review `.env` — at minimum change `SECRET_KEY` and the Postgres/MinIO credentials away from the placeholder values before doing anything beyond local dev.

## 2. Docker named volumes (required — compose does *not* create these for you)

`docker-compose.yaml` declares the Postgres and MinIO volumes as `external: true`, so they must exist before `docker compose up`:

```bash
docker volume create bytebattles_postgres
docker volume create bytebattles_minio
```

## 3. Build the sandbox images

The judge leases containers from `judge-gcc`, `judge-python`, and `judge-java` images. Build them once (and again any time you touch `judge/images/*`):


```bash
cd judge/images
./build_command.sh
cd ../..
```

## 4. Bring the stack up

```bash
docker compose up --build
```

This starts `postgres`, `redis`, `minio`, the `api` (port `8000`), and the `judge` orchestrator. Tables are created automatically on API startup (`Base.metadata.create_all` in `api/app/main.py`) — there is no separate migration step yet.

## 5. Create the MinIO buckets

Storage code (`shared/core/storage.py`) does **not** auto-create buckets. After MinIO is up, create the two buckets named in `.env` (`TESTCASE_BUCKET`, `SUBMISSION_BUCKET` — defaults `bytebattles-testcases`, `bytebattles-submission-code`):

```bash
# via the MinIO console at http://localhost:9000 (login with S3_ACCESS_KEY / S3_SECRET_KEY), or:
docker run --rm --network container:$(docker compose ps -q minio) \
  --entrypoint /bin/sh minio/mc -c "
    mc alias set local http://localhost:9000 minioadmin minioadmin &&
    mc mb local/bytebattles-testcases &&
    mc mb local/bytebattles-submission-code"
```

## 6. Create your first admin user

Registration always creates a regular `USER`. To get an `ADMIN` (required to create problems/tags), register normally through `/auth/register`, then flip `user_type` to `ADMIN` directly in Postgres:

```bash
docker compose exec postgres psql -U postgres -d postgres \
  -c "UPDATE users SET user_type = 'ADMIN' WHERE username = 'your_username';"
```

(There is intentionally no admin-promotion endpoint yet — see [PROBLEM_STATEMENT.md](PROBLEM_STATEMENT.md).)

## 7. Verify it's alive

```bash
curl http://localhost:8000/docs
```

should return the FastAPI Swagger UI. `docs/endpoints.md` and `docs/openapi.json` describe the routes; `judge/Judge_Architecture.pdf` documents the judge's internals in depth — read it before touching `judge/`.

## 8. Running api/judge outside Docker (faster local iteration)

```bash
uv sync --group api --group judge
```

Point `.env` at `localhost` instead of the service names (`DB_HOST=localhost`, `REDIS_HOST=localhost`, `S3_ENDPOINT_URL=http://localhost:9000`), keep Postgres/Redis/MinIO running via `docker compose up postgres redis minio`, then:

```bash
uv run uvicorn api.app.main:app --reload          # API, in one shell
uv run python -m judge.run                        # judge orchestrator, in another
```

The judge orchestrator needs a working Docker daemon reachable from wherever it runs (it shells out to the Docker API to manage sandbox containers).

## 9. Logs

Both services log to `./logs/` (mounted into the containers) — `logs/orchestrator.log` and friends. Tail these first when something isn't judging.
