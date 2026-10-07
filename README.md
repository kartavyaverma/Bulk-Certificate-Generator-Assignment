# Bulk Certificate Generator

A backend API that accepts one request containing many recipients, generates a PDF certificate for each of them from a single predefined template, tracks the progress of the whole batch, and lets the client download the results one by one or as a ZIP archive.

Built with **FastAPI**, **PostgreSQL**, **SQLAlchemy 2** and **ReportLab**, managed with **uv**.

---

## Contents

1. [What it does](#what-it-does)
2. [Tech stack](#tech-stack)
3. [Project structure](#project-structure)
4. [Setup](#setup)
5. [Running the application](#running-the-application)
6. [Running the tests](#running-the-tests)
7. [API overview](#api-overview)
8. [Submitting a certificate generation request](#submitting-a-certificate-generation-request)
9. [Checking progress](#checking-progress)
10. [Retrieving generated certificates](#retrieving-generated-certificates)
11. [Validation rules](#validation-rules)
12. [Statuses](#statuses)
13. [Design decisions](#design-decisions)
14. [Limitations and next steps](#limitations-and-next-steps)

---

## What it does

| Requirement | How it is met |
|---|---|
| Accept a certificate generation request | `POST /api/v1/jobs` takes the course details and a list of recipients |
| Validate recipient data | Every recipient is validated on its own; invalid ones are recorded with a reason and the valid ones continue |
| Generate a certificate per valid recipient | A landscape A4 PDF is drawn from one fixed template |
| Track generation status | A `jobs` row for the batch and one `certificates` row per recipient, each with its own status |
| Check progress and result | `GET /api/v1/jobs/{job_id}` returns the job status and live counts |
| Retrieve generated certificates | Download a single PDF, or every generated PDF of a job as a ZIP |
| Bulk rather than one request per certificate | One request can carry up to 10,000 recipients (configurable) |
| One failure must not stop the rest | Each certificate is generated and committed independently |

## Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| Web framework | FastAPI |
| Database | PostgreSQL |
| ORM and driver | SQLAlchemy 2 with psycopg 3 |
| Validation and settings | Pydantic v2 and pydantic-settings |
| PDF generation | ReportLab |
| Tests | pytest with FastAPI's `TestClient`, pypdf to read generated PDFs |
| Tooling | uv for the environment and dependencies, Docker Compose for PostgreSQL |

## Project structure

```
.
├── app/
│   ├── main.py              application object, startup, health check
│   ├── config.py            settings read from the environment / .env
│   ├── database.py          engine, session factory, declarative base
│   ├── models.py            Job and Certificate tables, status enums
│   ├── schemas.py           request and response models
│   ├── routers/
│   │   ├── jobs.py          submit, status, list, ZIP download
│   │   └── certificates.py  single certificate status and PDF download
│   └── services/
│       ├── validation.py    per-recipient validation
│       ├── jobs.py          job creation and read queries
│       ├── processor.py     background worker and restart recovery
│       ├── generator.py     the certificate template
│       └── storage.py       file locations, download names, ZIP building
├── tests/                   43 tests, one file per area
├── examples/request.json    sample request body
├── docker-compose.yml       PostgreSQL for local development
├── .env.example             configuration template
├── pyproject.toml
└── uv.lock
```

## Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Docker Desktop, **or** an existing PostgreSQL server

uv downloads Python 3.12 by itself if it is not installed.

### 1. Clone and install

```bash
git clone <repository-url>
```

```bash
cd bulk-certificate-generator
```

```bash
uv sync
```

`uv sync` creates `.venv` and installs the exact versions pinned in `uv.lock`, including the test dependencies.

### 2. Start PostgreSQL

```bash
docker compose up -d
```

This starts PostgreSQL 17 on **port 5433** with user `postgres`, password `postgres` and a database named `certificates`. Port 5433 is used so it does not collide with a PostgreSQL already installed on 5432.

### 3. Create the configuration file

macOS / Linux / Git Bash:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5433/certificates` | Application database |
| `TEST_DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5433/certificates_test` | Database used by the tests; its name must end in `_test` |
| `STORAGE_DIR` | `storage` | Folder where generated PDFs are written |
| `MAX_RECIPIENTS_PER_JOB` | `10000` | Largest recipient list accepted in one request |

### Using your own PostgreSQL instead of Docker

Create a database and point `DATABASE_URL` at it:

```sql
CREATE DATABASE certificates;
```

```
DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/certificates
TEST_DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/certificates_test
```

The tables are created automatically when the application starts.

## Running the application

```bash
uv run uvicorn app.main:app --port 8000
```

- Interactive API docs (Swagger UI): http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

Add `--reload` during development to restart on code changes.

> On Windows, prefer `127.0.0.1` over `localhost` in client calls. `localhost` is tried over IPv6 first and adds roughly two seconds to every request.

## Running the tests

PostgreSQL must be running. The test setup creates the `certificates_test` database by itself if it does not exist, builds the tables, and empties them between tests. Generated PDFs go to a temporary folder that is removed afterwards.

```bash
uv run pytest
```

Verbose output:

```bash
uv run pytest -v
```

| File | What it covers |
|---|---|
| `tests/test_job_creation.py` | Creating a generation job, stored rows, many recipients in one request |
| `tests/test_validation.py` | Request level and recipient level input validation, duplicates, limits |
| `tests/test_generation.py` | The PDF template and that each recipient gets a file with their details |
| `tests/test_job_status.py` | Status and progress before and after processing, restart recovery |
| `tests/test_failure_handling.py` | One certificate failing while the others in the job succeed |
| `tests/test_retrieval.py` | Listing, filtering, pagination, PDF download, ZIP download |

## API overview

Base path: `/api/v1`

| Method | Path | Purpose | Success |
|---|---|---|---|
| `POST` | `/jobs` | Submit a bulk generation job | `202` |
| `GET` | `/jobs/{job_id}` | Job status and progress | `200` |
| `GET` | `/jobs/{job_id}/certificates` | List the certificates of a job, with `status`, `limit`, `offset` | `200` |
| `GET` | `/jobs/{job_id}/download` | ZIP of every generated certificate | `200` |
| `GET` | `/certificates/{certificate_id}` | Status of one certificate | `200` |
| `GET` | `/certificates/{certificate_id}/download` | One certificate as a PDF | `200` |
| `GET` | `/health` | Confirms the API can reach the database | `200` |

Error responses:

| Code | When |
|---|---|
| `404` | Unknown job or certificate, a job with nothing generated, or a PDF missing from storage |
| `409` | Downloading a certificate that is not generated, or a job ZIP before the job has finished |
| `422` | Malformed request, an empty or oversized recipient list, or a request in which no recipient is valid |
| `503` | `/health` cannot reach the database |

## Submitting a certificate generation request

`examples/request.json` contains three valid recipients, one with a broken email and one duplicate.

curl (macOS / Linux / Git Bash):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/jobs -H "Content-Type: application/json" --data-binary @examples/request.json
```

Windows PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/jobs -ContentType "application/json; charset=utf-8" -InFile examples/request.json | ConvertTo-Json -Depth 5
```

Or open http://127.0.0.1:8000/docs, expand `POST /api/v1/jobs`, press **Try it out** and **Execute**.

### Request body

| Field | Type | Required | Rules |
|---|---|---|---|
| `course_name` | string | yes | 2 to 120 characters |
| `issuer_name` | string | yes | 2 to 80 characters |
| `issue_date` | date `YYYY-MM-DD` | no | Defaults to today |
| `recipients` | array of objects | yes | 1 to `MAX_RECIPIENTS_PER_JOB` items |
| `recipients[].name` | string | yes | 2 to 80 characters, at least one letter |
| `recipients[].email` | string | yes | Valid email, unique within the request |

### Response `202 Accepted`

The response is returned as soon as the job is stored. Generation continues in the background.

```json
{
  "id": "379c1548-c1e5-4a3a-8e0b-f5631ed82318",
  "course_name": "Python Backend Bootcamp",
  "issuer_name": "Acme Academy",
  "issue_date": "2026-10-07",
  "status": "pending",
  "progress": {
    "total": 5,
    "pending": 3,
    "generated": 0,
    "failed": 0,
    "invalid": 2,
    "percent_complete": 40.0
  },
  "created_at": "2026-10-07T09:48:54.101Z",
  "started_at": null,
  "completed_at": null,
  "links": {
    "status": "/api/v1/jobs/379c1548-c1e5-4a3a-8e0b-f5631ed82318",
    "certificates": "/api/v1/jobs/379c1548-c1e5-4a3a-8e0b-f5631ed82318/certificates",
    "download": "/api/v1/jobs/379c1548-c1e5-4a3a-8e0b-f5631ed82318/download"
  },
  "invalid_recipients": [
    {
      "id": "0d2f6c1e-5d5e-4d8a-9a0e-3c0f8f1c7b11",
      "job_id": "379c1548-c1e5-4a3a-8e0b-f5631ed82318",
      "position": 3,
      "recipient_name": "Broken Email",
      "recipient_email": "not-an-email",
      "status": "invalid",
      "error": "email: value is not a valid email address: An email address must have an @-sign.",
      "generated_at": null,
      "download_url": null
    },
    {
      "id": "7b0c9d55-2f1b-4a8e-8a53-0f4a0f0b6c22",
      "job_id": "379c1548-c1e5-4a3a-8e0b-f5631ed82318",
      "position": 4,
      "recipient_name": "Asha Duplicate",
      "recipient_email": "ASHA.RAO@example.com",
      "status": "invalid",
      "error": "email: duplicate of an earlier recipient in this request",
      "generated_at": null,
      "download_url": null
    }
  ]
}
```

`position` is the zero-based index of the recipient in the submitted `recipients` array, so the client can match every result back to its input row.

Keep the `id`; it is used in every following call.

## Checking progress

```bash
curl http://127.0.0.1:8000/api/v1/jobs/<job_id>
```

The response has the same shape as the one above without `invalid_recipients`. The fields that change are shown here:

```json
{
  "id": "379c1548-c1e5-4a3a-8e0b-f5631ed82318",
  "status": "completed_with_errors",
  "progress": {
    "total": 5,
    "pending": 0,
    "generated": 3,
    "failed": 0,
    "invalid": 2,
    "percent_complete": 100.0
  },
  "started_at": "2026-10-07T09:48:54.180Z",
  "completed_at": "2026-10-07T09:48:54.650Z"
}
```

Poll this endpoint until `status` is no longer `pending` or `processing`.

To see exactly which recipients succeeded or failed:

```bash
curl "http://127.0.0.1:8000/api/v1/jobs/<job_id>/certificates?status=failed"
```

```bash
curl "http://127.0.0.1:8000/api/v1/jobs/<job_id>/certificates?status=invalid"
```

Each item carries the recipient, its `status`, and an `error` message when it did not succeed.

## Retrieving generated certificates

### List the certificates of a job

```bash
curl "http://127.0.0.1:8000/api/v1/jobs/<job_id>/certificates?status=generated&limit=100&offset=0"
```

```json
{
  "total": 3,
  "limit": 100,
  "offset": 0,
  "items": [
    {
      "id": "5d2277f9-6156-46b0-a1ba-87ff3576f005",
      "job_id": "379c1548-c1e5-4a3a-8e0b-f5631ed82318",
      "position": 0,
      "recipient_name": "Asha Rao",
      "recipient_email": "asha.rao@example.com",
      "status": "generated",
      "error": null,
      "generated_at": "2026-10-07T09:48:54.310Z",
      "download_url": "/api/v1/certificates/5d2277f9-6156-46b0-a1ba-87ff3576f005/download"
    }
  ]
}
```

`limit` accepts 1 to 500 and defaults to 100.

### Download one certificate

```bash
curl -o asha-rao.pdf http://127.0.0.1:8000/api/v1/certificates/<certificate_id>/download
```

### Download every certificate of a job as a ZIP

```bash
curl -o certificates.zip http://127.0.0.1:8000/api/v1/jobs/<job_id>/download
```

The archive contains only the certificates that were generated, named `<recipient-name>-<short-id>.pdf`. It is available once the job has finished.

## Validation rules

Validation happens at two levels, on purpose.

**Request level.** If the envelope is wrong the whole request is rejected with `422` and nothing is stored: a missing or blank `course_name` or `issuer_name`, a malformed `issue_date`, an empty `recipients` array, or more recipients than `MAX_RECIPIENTS_PER_JOB`.

**Recipient level.** Each recipient is validated separately. A bad recipient does not reject the request; it is stored with status `invalid` and an `error` explaining why, and it is returned in `invalid_recipients`. The remaining recipients are processed normally. A recipient is invalid when:

- `name` is missing, shorter than 2 or longer than 80 characters, or contains no letter
- `email` is missing or not a valid address
- `email` repeats an earlier recipient in the same request, compared case-insensitively

Names are trimmed and repeated spaces collapsed before they are stored and printed.

If **no** recipient in the request is valid, there is nothing to generate, so the request is rejected with `422` and the list of reasons, and no job is created.

## Statuses

### Job

| Status | Meaning |
|---|---|
| `pending` | Stored, generation has not started |
| `processing` | Certificates are being generated |
| `completed` | Every recipient got a certificate |
| `completed_with_errors` | At least one certificate was generated and at least one recipient was invalid or failed |
| `failed` | Generation ran and no certificate could be produced |

### Certificate

| Status | Meaning |
|---|---|
| `pending` | Valid recipient, waiting to be generated |
| `generated` | PDF exists and can be downloaded |
| `failed` | Generation was attempted and raised an error; see `error` |
| `invalid` | Rejected by validation, generation was never attempted; see `error` |

## Design decisions

### Background processing instead of generating inside the request

`POST /jobs` validates, stores the job and its recipient rows in one transaction, schedules the work with FastAPI's `BackgroundTasks`, and returns `202 Accepted` immediately. The client then polls the status endpoint.

Generating synchronously would keep one HTTP connection open for the entire batch. That is slow for the client, likely to hit a proxy or client timeout on a large list, and loses everything if the connection drops. With background processing the request stays fast regardless of batch size (about one second for 2,000 recipients on a laptop, almost all of it inserting rows) and progress is observable while the work runs.

`BackgroundTasks` was chosen over Celery or RQ because it needs no extra infrastructure: no broker, no separate worker process, nothing more for a reviewer to install. The trade-off is that the work runs inside the web process, which is addressed next.

### Surviving a restart

Because the queue is in memory, a restart in the middle of a job would normally lose it. Two things prevent that:

- The job and every recipient row are committed to PostgreSQL **before** the background task is scheduled, so the database always knows what work exists.
- On startup the application looks for jobs still in `pending` or `processing` and resumes them. Only certificates still marked `pending` are generated, so finished ones are never redone.

### One row per recipient, committed one at a time

Every recipient gets a `certificates` row with its own status and error. The worker generates one PDF, updates that row, and commits before moving to the next. This gives three things at once: a failure is isolated to its own row, progress is accurate while the job runs, and a crash loses at most the certificate in flight.

### Failure isolation

Generation of each certificate runs inside its own `try/except`. An exception is logged, the row is marked `failed` with the exception type and message, and the loop continues. The job finishes as `completed_with_errors` rather than aborting.

### Partial acceptance of recipients

A list of 500 with three typos should produce 497 certificates and a clear report on the other three, not a rejection that forces the client to fix and resubmit everything. Invalid recipients are stored rather than dropped so the job remains a complete record of what was submitted. `invalid` is kept separate from `failed` because they mean different things: `invalid` is the client's data and will never succeed as submitted, `failed` is a problem on our side during generation.

### Progress is computed, not stored

The counts come from a `GROUP BY status` query over the job's certificate rows, backed by an index on `(job_id, status)`. There are no counter columns on the job that could drift out of sync with the rows they describe.

### Template and PDF library

ReportLab draws the certificate directly onto a PDF canvas. It is pure Python with no system dependencies, unlike HTML to PDF tools that need a browser engine or native libraries, so `uv sync` is the whole installation on every platform. It is also fast, at a few milliseconds of CPU per certificate. The template lives in one module and takes a small data object, so it has no knowledge of the database or HTTP.

Long names and course titles are shrunk to fit the page width instead of overflowing. Each certificate prints its own unique ID.

### Files are written atomically

A PDF is written to a `.tmp` file and then renamed into place. A reader can never download a half-written certificate, and a crash during writing leaves no file that looks valid.

### Files on disk, paths in the database

PDFs are stored under `STORAGE_DIR/<job_id>/<certificate_id>.pdf` and the database stores only the relative path. Binary files in PostgreSQL bloat the database and its backups; the filesystem serves them more efficiently. Because all path handling is in `services/storage.py`, moving to object storage such as S3 means changing that one module.

### Statuses as text, not native PostgreSQL enums

Status columns are `VARCHAR` values mapped to Python enums by SQLAlchemy. Adding a status later is a code change only, with no `ALTER TYPE` migration.

### UUID identifiers

Job and certificate IDs are UUIDs. They are not guessable, which matters because the download URL contains the ID, and they do not reveal how many certificates exist.

### Layered structure

Routers handle HTTP only. Services hold the logic and know nothing about HTTP. Models describe tables and schemas describe the API contract. Each layer can be tested and changed without touching the others; for example the tests exercise the generator and the validator directly, without going through the API.

## Limitations and next steps

These were left out deliberately to keep the required functionality solid.

- **Single process.** Work runs in the web process and restart recovery assumes one instance. With several workers or instances the same job could be resumed twice. The next step is a real task queue (Celery, RQ or arq with Redis) or a worker that claims jobs with `SELECT ... FOR UPDATE SKIP LOCKED`. Only `process_job` would need a different caller.
- **No schema migrations.** Tables are created with `create_all` at startup. A real deployment would use Alembic.
- **No authentication.** Anyone who can reach the API can submit jobs and download certificates. UUIDs make URLs unguessable but are not access control.
- **Latin script only.** The template uses the standard PDF fonts, which cover Western European characters. A name in another script is not printed incorrectly; that certificate is marked `failed` with a clear reason. Supporting more scripts means embedding a Unicode font.
- **Sequential generation.** Certificates in a job are generated one after another. Measured at roughly 15 ms each on a development laptop, including the database commit. A process pool would parallelise this if needed.
- **No retry endpoint.** A failed certificate stays failed. A `POST /jobs/{id}/retry` that resets `failed` rows to `pending` and schedules `process_job` again would be a small addition.
- **Local file storage.** Suitable for a single server; object storage is the production choice.
