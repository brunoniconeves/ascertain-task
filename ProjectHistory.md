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

- Middleware for Logging
    - The logging middleware should capture request/response metadata, latency, and correlation IDs, but never log PHI or request bodies. Domain events are logged at the service layer. This separation keeps logs useful, secure, and scalable.

    - Middleware is tested by asserting observable behavior — headers and structured logs — not by inspecting internal implementation. I use caplog to verify contracts without coupling tests to log formats.


## 2025-12-18 - Part 2 - Extended notes endpoints

Notes are a child resource of patients, so the API is patient-scoped. This keeps ownership, authorization, pagination, and auditing simple and explicit. A top-level notes endpoint would only make sense for cross-patient analytics, which isn’t the case here.

- Local storage, since it's a test and add S3 will cause a lot of additional steps to configure the project, I decided to keep notes in local storage. For production, consider using a bucket solution with encryption on AWS,Azure or other service provider.

- ID choice: Notes use UUID to match patients.id (already UUID) and to avoid leaking ordering/volume signals that sequential integers can reveal.

- Storage model: A note is either inline (content_text) or file-backed (file_path + metadata); a DB constraint enforces this (no ambiguous precedence).

- File truth: When file-backed, the filesystem object is the source of truth; any extracted text is stored separately (see patient_note_text).

- Optional patient_note_text: Enables search/OCR/NLP while keeping patient_notes.content_text reserved for true inline notes; trade-off is duplicating PHI (so you can apply different retention/access controls later).

- Constraints: Check constraint ensures at least one of content_text/file_path exists; additional guards prevent absolute paths / .. traversal and validate SHA-256 length.

- Time validity: taken_at has a DB check taken_at <= now() (and should also be validated at the API layer for clearer client errors).
Indexes: patient_id index + composite (patient_id, taken_at) index for efficient per-patient listing/sorting.

- PHI safety: No redundant patient attributes are stored; file_path is intended as a relative, PHI-free key under a configurable base dir like ./data/notes/.

- Deletion strategy: Soft delete via deleted_at for auditability (common healthcare need to retain historical metadata/lineage while hiding from normal reads).

- Future S3 support: Treat file_path as a storage key (relative path/object key) and keep checksum/size/mime; swapping filesystem→S3 can be done in application storage code without changing this schema.

    




