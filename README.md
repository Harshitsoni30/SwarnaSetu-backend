# API

FastAPI service for SwarnaSetu. It exposes a health check and the public account routes.

## Run locally

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`GET /health` returns `{ "status": "ok" }`.

Account routes are `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/forgot-password`, `/auth/reset-password`, and `/auth/google`. They are mounted when `APP_DATABASE_URL` is set.

Copy `.env.example` to `.env` for local settings. Do not put real secrets in the example file.

## Checks

```bash
pytest
ruff check src tests
mypy
```

## Docker

```bash
docker build -t mobile-api:local .
docker run --rm -p 8000:8000 mobile-api:local
```

The image listens on port 8000 and runs as a non-root user.
