# ascertain-task

FastAPI + Postgres backend for storing and retrieving patient medical records, notes and summary generation.
This was part of a take home task for a Ascertain senior developer role.

## API endpoints

- `GET /health` returns `{"status": "ok"}`
- Patient CRUD:
  - `GET /patients` (paging + optional sorting/filtering)
  - `GET /patients/{patient_id}`
  - `POST /patients`
  - `PUT /patients/{patient_id}`
  - `DELETE /patients/{patient_id}`
  - `POST /patients/{patient_id}/notes`
  - `GET /patients/{patient_id}/notes`
  - `DELETE /patients/{patient_id}/notes/{note_id}`
  - ``


Interactive docs:

- ReDoc (read-only): `GET /docs`
- Swagger UI (“Try it out”): `GET /swagger`

The OpenAPI JSON is available at `GET /openapi.json`.

## Seed data

On container start (in Docker), the API runs seed steps for local development:

- **Patients**: inserts **15 patients** only if:
  - `APP_ENV=development`
  - the `patients` table is currently empty

- **Patient notes**: after patients exist, it seeds **3 SOAP notes per seeded patient** (total **45 notes**),
  by calling the same API endpoint used by normal clients (`POST /patients/{patient_id}/notes`), so the
  **derived structured SOAP data** is created and persisted as part of the normal ingestion flow.

SOAP seed inputs come from `data/exampleFiles/ai_generated_soap_*.txt` (synthetic examples; no real PHI).

## Local setup (Docker Compose)

1. Create your `.env` from the example:

```bash
cp .env.example .env
```

2. Start Postgres + API:

```bash
docker compose up --build
```

### Start from scratch (wipe DB + rebuild everything)

If you want a clean database and the seed to run again, remove containers, images, and volumes, then start up:

```bash
docker compose down --remove-orphans --rmi all -v
docker compose up -d --build
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

## 📝 Patient Notes & SOAP Handling

This API supports storing patient notes as part of a patient’s medical record. Notes may be provided as **plain text** or as **uploaded files**, and may optionally follow the **SOAP (Subjective, Objective, Assessment, Plan)** clinical format.

### Core Design Principle

The system explicitly separates:

- **Raw clinical notes** → **authoritative source of truth**
- **Structured data** → **derived, non-authoritative metadata**

The original note content is always preserved exactly as provided. Any structured data extracted from it never replaces or modifies the original note. This mirrors real healthcare and compliance requirements, where original clinical documentation must remain intact for auditability and legal purposes.


## Supported Inputs

SOAP-formatted notes may be submitted in either form:

1. A `.txt` file upload containing SOAP content  
2. Plain text in the request body using the same SOAP format  

Once raw text is available, both inputs are handled identically by the system.



## SOAP Parsing Behavior

When `note_type = "soap"` is explicitly provided, the system attempts a **deterministic, best-effort parse** of the note into SOAP sections:

- **S** – Subjective  
- **O** – Objective  
- **A** – Assessment  
- **P** – Plan  

Parsing rules:
- Based only on explicit section markers (`S:`, `O:`, `A:`, `P:`)
- Missing or partial sections are allowed
- Parsing failures **never block ingestion**
- No AI, NLP, or inference is used

If parsing succeeds, structured data is stored as derived metadata. If parsing fails, the raw note is still stored and the request succeeds.



## Data Flow (Diagram)

> The diagram above illustrates how raw clinical notes are ingested, preserved as the source of truth, and optionally parsed into derived SOAP-structured data.


<p align="center">
  <img src="docs/diagrams/note-flow-diagram.png" alt="SOAP Note Ingestion Flow" width="700"/>
</p>


## Structured Data Storage

When available, parsed SOAP data is stored separately from the raw note as structured JSON, for example:

```json
{
  "schema": "soap_v1",
  "parser_version": "v1",
  "sections": {
    "subjective": "...",
    "objective": "...",
    "assessment": "...",
    "plan": "..."
  }
}
```

## Get Notes endpoint

When available, derived structured data (e.g. parsed SOAP sections) is returned alongside the raw note. This data is optional, non-authoritative, and explicitly marked as derived.

### Pagination endpoint vs single-note endpoint
For list endpoint (GET /patients/{id}/notes)

We do not return structured data because:

- Structured data is bigger

For detailed endpoint (GET /patients{id}/notes/{id})

We return detailed derived data if available


## Why This Design

- Preserves clinical and legal integrity

- Enables structured querying without data loss

- Parsing is transparent, explainable, and non-blocking

- Avoids overengineering and unsafe inference

- Reflects real-world healthcare system constraints

In a production system, structured data could later be augmented by OCR or NLP tools, but the clinician-provided note would always remain the authoritative record.


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
