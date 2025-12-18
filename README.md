# ascertain-task

FastAPI + Postgres backend for storing and retrieving patient medical records.

## Part 1 scope

- `GET /health` returns `{"status": "ok"}`
- Patient CRUD:
  - `GET /patients` (paging + optional sorting/filtering)
  - `GET /patients/{id}`
  - `POST /patients`
  - `PUT /patients/{id}`
  - `DELETE /patients/{id}`

Interactive docs:

- ReDoc (read-only): `GET /docs`
- Swagger UI (“Try it out”): `GET /swagger`

The OpenAPI JSON is available at `GET /openapi.json`.

## Seed data

On container start, the API runs a small seed step that inserts **15 patients only if**:

- `APP_ENV=development`
- the `patients` table is currently empty

## Local setup (Docker Compose)

1. Create your `.env` from the example:

```bash
cp .env.example .env
```

2. Start Postgres + API:

```bash
docker compose up --build
```

3. Verify:

```bash
curl -s localhost:8000/health
```

## API behavior

### `GET /patients` (pagination + optional filtering/sorting)

Query params:

- `limit`: 1..100 (default 50)
- `cursor`: opaque cursor string returned as `next_cursor` from the previous page
- `name`: optional case-insensitive substring match on `name` (**min 3 chars**)
- `sort`: `name | date_of_birth | created_at`
- `order`: `asc | desc` (default `asc`)

Response shape:

```json
{
  "items": [],
  "limit": 50,
  "next_cursor": null
}
```

### Create a patient

```bash
curl -s -X POST localhost:8000/patients \
  -H 'Content-Type: application/json' \
  -d '{"name":"Ada Lovelace","date_of_birth":"1815-12-10"}'
```

## Logging & security (HIPAA/LGPD-aware)

This service includes an HTTP logging middleware that is designed to be safe in healthcare environments.

What is logged (metadata only):

- `request_id` (correlation id via `X-Request-ID`)
- HTTP method
- request path (**no query string**)
- response status code
- request duration (ms)

What is **never** logged:

- request bodies / response bodies
- query parameter values (may contain PHI)
- sensitive headers (e.g. `Authorization`, cookies)

FUTURE DEVELOPMENT:
OpenTelemetry standard implementation.

Correlation ID:

- The middleware **propagates** a valid incoming `X-Request-ID` or **generates** one.
- `X-Request-ID` is added to **all** responses so logs can be correlated end-to-end.

Also added business logic basic validation and logging (example in pacient creation that validates date of birth)

## Database migrations

Migrations are managed with Alembic.

- In Docker, migrations run automatically on container start.
- Locally, you can run:

```bash
export DATABASE_URL='postgresql+asyncpg://postgres:postgres@localhost:5432/ascertain'
alembic upgrade head
```

## Tests

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

## Formatting (Ruff)

Ruff is configured as the formatter and linter.

```bash
ruff format .
ruff check --fix .
```
