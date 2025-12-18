## 2025-12-17 — Part 1 (backend foundation)

- Implemented FastAPI app with `GET /health`.

- Added Postgres-backed patient storage using async SQLAlchemy + Alembic migrations.

- Decided to follow a Vertical Slices pattern by features
    - it fits any project and scales batter

- Implemented patient CRUD endpoints with pagination and basic sorting/filtering.

    - Decided to use cursor pagination because in a context of a large health application, we can expect a database to have hundreds of thausands of pacients to paginate.
        - Stable results even with inserts/deletes
        - O(1) performance per page
        - No skipping or duplication
        - Safe for large datasets
        - Data correctness (this is critical)
            - If a patient is admitted or discharged between requests:
                - Patients can move between pages
                - You can skip or duplicate patients
        - No jump to page (con)
            - If “jump to patient” is needed → search, not pagination.
- Added Dockerfile + docker-compose for local dev.

- Added pytest coverage for health + patient CRUD flow.
