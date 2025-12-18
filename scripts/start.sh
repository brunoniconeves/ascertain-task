#!/bin/sh
set -eu

cd /app
export PYTHONPATH="/app"

# Try to ensure ReDoc JS is available locally (avoids blank docs when CDN is blocked).
REDOC_JS_PATH="/app/app/static/redoc.standalone.js"
if [ ! -f "$REDOC_JS_PATH" ]; then
  echo "Fetching ReDoc JS into $REDOC_JS_PATH ..."
  mkdir -p "$(dirname "$REDOC_JS_PATH")"
  curl -fsSL "https://cdn.jsdelivr.net/npm/redoc@2.1.4/bundles/redoc.standalone.js" -o "$REDOC_JS_PATH" || \
    echo "Warning: failed to download ReDoc JS (docs may be blank if CDN is blocked)."
fi

echo "Waiting for database to be ready..."
python - <<'PY'
import asyncio
import os
import sys

DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    print("DATABASE_URL is not set", file=sys.stderr)
    sys.exit(1)

# No readiness needed for local sqlite URLs.
if DATABASE_URL.startswith("sqlite"):
    print("SQLite detected; skipping DB readiness wait.")
    sys.exit(0)

# SQLAlchemy URL -> asyncpg URL
asyncpg_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

async def main() -> None:
    try:
        import asyncpg  # type: ignore
    except Exception as exc:
        print(f"asyncpg not available: {exc}", file=sys.stderr)
        sys.exit(1)

    last_exc: Exception | None = None
    for attempt in range(1, 61):
        try:
            conn = await asyncpg.connect(asyncpg_url, timeout=2)
            await conn.close()
            print("Database is ready.")
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt in {1, 5, 10, 20, 40, 60}:
                print(f"DB not ready yet (attempt {attempt}/60): {type(exc).__name__}: {exc}")
            await asyncio.sleep(1)

    print(f"Database was not ready after 60s. Last error: {type(last_exc).__name__}: {last_exc}", file=sys.stderr)
    sys.exit(1)

asyncio.run(main())
PY

echo "Running migrations..."
alembic upgrade head

echo "Seeding patients (only if empty)..."
python /app/scripts/seed_patients.py

echo "Starting API..."
uvicorn app.main:app --host 0.0.0.0 --port 8000


