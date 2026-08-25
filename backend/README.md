# aptori backend

Headless core for the social intelligence and engagement copilot: FastAPI application services over PostgreSQL canonical state, with Alembic-managed schema.

## Requirements

- Python 3.12+ (managed automatically by [uv](https://docs.astral.sh/uv/))
- PostgreSQL reachable via peer/trust auth or `APTORI_DATABASE_URL`

## Setup

```bash
cd backend
~/.local/bin/uv sync

# Development database (adjust if not using local peer auth)
createdb aptori_outreach            # or: APTORI_DATABASE_URL=... in backend/.env

# Apply migrations
~/.local/bin/uv run alembic upgrade head

# Run the API
~/.local/bin/uv run uvicorn app.main:app --reload
```

`GET /health` returns `{"status": "ok", "database": "ok"}` and degrades to HTTP 503 when the database is unreachable. PostgreSQL connection establishment is bounded by `APTORI_DATABASE_CONNECT_TIMEOUT_SECONDS` (default 3 seconds).

The first domain slice is live: `POST /campaigns` creates a draft Campaign in the seeded default Workspace; `GET /campaigns?limit=50&cursor=…` returns a newest-first page; `GET/PATCH /campaigns/{id}` reads, edits, and walks the lifecycle (`DRAFT → ACTIVE → PAUSED → ACTIVE; ACTIVE|PAUSED → ARCHIVED`); and `GET /campaigns/{id}/audit` exposes the authorized append-only history in bounded pages. Page cursors are opaque and endpoint-scoped.

Every Campaign route requires `Authorization: Bearer <APTORI_API_TOKEN>` (set `APTORI_API_TOKEN` in `.env`; an empty value is treated as unset, and while unset the API fails closed with `api_token_unconfigured`). `GET /health` and the generated API documentation remain public deliberately. Campaign writes additionally require a unique `Idempotency-Key` per logical write; retries replay the originally recorded success or deterministic domain error without re-executing.

## Tests

The suite migrates a dedicated test database (`aptori_outreach_test`, override with `APTORI_TEST_DATABASE_URL`) and creates it when missing:

```bash
~/.local/bin/uv run pytest
```

`TestClient` drives the app in-process over [httpx2](https://pypi.org/project/httpx2/), Starlette's current TestClient transport and a dev-only dependency; nothing in `app/` imports it.

## Static checks (CI gates)

CI runs these checks with Python 3.12 after `uv sync --frozen`; all three type
checkers must pass before merge. Run the same sequence locally from `backend/`:

```bash
~/.local/bin/uv python install 3.12
~/.local/bin/uv sync --frozen
~/.local/bin/uv run mypy                    # strict mode + pydantic plugin
~/.local/bin/uv run ty check app tests      # Astral ty
~/.local/bin/uv run pyrefly check           # Meta pyrefly (pyrefly.toml)
~/.local/bin/uv run pytest
```

Configuration lives in `pyproject.toml` (`[tool.mypy]`, `[tool.pydantic-mypy]`) and `pyrefly.toml`. Annotation conventions: PEP 604/585 syntax, parameterized generics, no bare `Callable`; never suppress missing-annotation errors.

Configuration is environment-driven with the `APTORI_` prefix (see `app/config.py`). Copy `.env.example` to the git-ignored `backend/.env`; the backend resolves that file relative to its own package, independent of the process working directory. Production deployments should inject environment variables directly.
