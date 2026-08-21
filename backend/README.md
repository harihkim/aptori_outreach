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

`GET /health` returns `{"status": "ok", "database": "ok"}` and degrades to HTTP 503 when the database is unreachable.

## Tests

The suite migrates a dedicated test database (`aptori_outreach_test`, override with `APTORI_TEST_DATABASE_URL`) and creates it when missing:

```bash
~/.local/bin/uv run pytest
```

## Static checks

Three type checkers guard the codebase; all must pass before merge:

```bash
~/.local/bin/uv run ty check app tests      # Astral ty
~/.local/bin/uv run mypy                    # strict mode + pydantic plugin
~/.local/bin/uv run pyrefly check           # Meta pyrefly (pyrefly.toml)
```

Configuration lives in `pyproject.toml` (`[tool.mypy]`, `[tool.pydantic-mypy]`) and `pyrefly.toml`. Annotation conventions: PEP 604/585 syntax, parameterized generics, no bare `Callable`; never suppress missing-annotation errors.

Configuration is environment-driven with the `APTORI_` prefix (see `app/config.py`); a local `.env` is git-ignored.
