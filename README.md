# TERA — Travel Expense Review Assistant

TERA organizes PDF receipts by employee and trip, then generates a German expense report. It includes a German React interface, a FastAPI backend, Postgres, S3-compatible storage, and Ollama.

**Employee → Trip → Upload PDFs → Generate summary**

Reports include dated expenses, separate totals for each currency, and four categories: **Hotel, Flugreisen, Verpflegung, Sonstige Ausgaben**. Accommodation details include breakfast amounts when available.

## Start with Docker

Install Docker Desktop and open it. Run these commands from the project folder.

### 1. Copy the settings

```bash
cp .env.example .env
```

If `.env` already exists, edit it instead of replacing it. The application uses one model, selected with `OLLAMA_MODEL` in this file.

### 2. Start the services

```bash
docker compose up --build -d
```

This starts the web interface, API, worker, Postgres, file storage, and Ollama. Setup services create the database tables and storage bucket, and download the selected model. The worker starts after the download succeeds. The first startup can take a while.

Docker keeps its Ollama files in a separate volume, so a model already installed on the host is not reused automatically. The command above can therefore download another copy. For day-to-day development, use the local setup below; it connects to the host Ollama installation directly. Only use the full Docker startup when an isolated deployment-style environment is required.

Check progress:

```bash
docker compose ps -a
docker compose logs -f model-init worker
```

Model files, uploaded PDFs, and the database are stored in persistent Docker volumes. Existing model files are reused on subsequent starts. Model files installed in a host Ollama installation are separate from the Docker volume.

### 3. Open the application

Open [localhost:3000](http://localhost:3000). The interface guides you through the normal workflow:

1. Add an employee.
2. Create a trip for that employee.
3. Upload the trip's PDF receipts.
4. Click **Auswertung erstellen**.
5. Review totals, categories, expenses, and flagged inconsistencies.

The API documentation remains available at [localhost:8000/docs](http://localhost:8000/docs).

### Stop and restart

```bash
docker compose stop
docker compose up -d
```

Stopping preserves your data. `docker compose down -v` deletes the project's stored data, including model files.

## Model settings

Change `OLLAMA_MODEL` in `.env` to select a different model. Then run:

```bash
docker compose up -d ollama
docker compose run --rm model-init
docker compose up -d --force-recreate api worker
```

Let active jobs finish before changing the model. The selected model is recorded with each report. The application has no model-name-specific behavior or fallback model list.

`OLLAMA_THINK=false` keeps Qwen's internal reasoning out of the structured response budget. Change it only when the selected model requires a different value. Context size, output budget, and timeout are also configured in `.env`. `OLLAMA_IMAGE` selects the Ollama container version; use a tested version or image digest for a deployment.

The default Docker configuration runs inference on CPU. On a Linux server with an NVIDIA GPU and NVIDIA Container Toolkit installed, use:

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up --build -d
```

See the official [Ollama Docker instructions](https://docs.ollama.com/docker) for GPU setup. On Apple Silicon, running Ollama directly on macOS is preferable for GPU acceleration; use the local development setup below.

To keep Postgres, file storage, the API, and the web interface in Docker while using the
existing macOS Ollama installation, start the stack with both Compose files:

```bash
docker compose -f compose.yaml -f compose.host-ollama.yaml up --build -d
```

Ollama must already be running on macOS and the selected model must already be installed.
This configuration does not install or update a model.

## Local development without Docker

Docker is not required while developing. The local setup uses SQLite and the `.local/documents` folder instead of Postgres and S3. A local Ollama installation must be running.

```bash
uv sync --locked
cd frontend && npm install && cd ..
make dev-setup
```

`make dev-setup` creates `.env.development`, the SQLite database, and local document storage. Run it again after a new database migration. Download the model named in `.env.development` with Ollama.

Start three development processes in separate terminals:

```bash
make dev-api
```

```bash
make dev-worker
```

```bash
make dev-web
```

Open [localhost:5173](http://localhost:5173). Python and React changes reload automatically, so Docker does not need to be rebuilt. Do not run the Docker API and local API at the same time because both use port 8000.

## Authentication

Users create an account with their name, email address, and a password of at least 12 characters. Passwords are stored as Argon2 hashes. The API returns a signed, expiring access token; Axios attaches it to protected requests and returns the user to the login screen when the session expires.

Set `AUTH_ALLOW_REGISTRATION=false` after creating the required accounts in a closed deployment. Set a unique `AUTH_SECRET_KEY` of at least 32 bytes and `APP_ENVIRONMENT=production` before production deployment. The default development secret is rejected when the production environment is selected.

## API and report data

`GET /summary-jobs/{id}/result` returns structured JSON:

- `coverage`: document counts and processing failures.
- `documents`: extracted totals, tax fields, line items, source quotations, and validation issues.
- `expenses`: dated expense rows with categories and source pages.
- `totals`: totals by date, category, and currency.
- `accommodation`: hotel and breakfast amounts.
- `warnings`: items requiring review.

Amounts are decimal strings such as `"712.60"`; missing values are `null`. The frontend uses this JSON directly for tables and filters. Response types are documented in `/docs` and `/openapi.json`.

Jobs have these states: `queued`, `running`, `completed`, `needs_review`, or `failed`. Progress is available through `completed_chunks` and `total_chunks`. Partial results identify failed documents explicitly. Completion is not an approval for reimbursement.

Generating a report captures the documents currently in the trip. Repeated requests return the active job instead of creating duplicates. Uploading another document makes an existing report `is_stale: true`; generate a new report to include it. Lists support `limit` and `offset`.

## Document processing

Uploads must be readable PDFs with selectable text. Default limits are 20 MB and 200 pages per file. Each PDF should contain one receipt or invoice, which can span multiple pages.

The worker splits document text into bounded requests while retaining page references. It uses a conservative UTF-8 byte budget with space reserved for instructions, output, and a possible correction request. Failed or truncated responses become review items.

The model keeps net, tax, and gross amounts separate and extracts individual expense lines with exact source quotations. Python checks invoice arithmetic, line totals, tax components, breakfast amounts, dates, categories, duplicates, and source evidence using `Decimal`. If a check fails, the affected document part is sent through one focused correction pass. Unresolved conflicts require review and are excluded from confirmed totals.

The German report is displayed from the validated JSON structure in a fixed layout. Each currency stays separate. A priced breakfast is assigned to `Verpflegung` once; an included breakfast without a stated price remains unknown.

An upload and a report generation are separate operations:

1. The API checks the PDF, extracts its existing text layer page by page, stores the original PDF in object storage, and stores the extracted pages in the database.
2. **Auswertung erstellen** creates a job containing the current document IDs, model name, and prompt version. The API responds immediately.
3. The worker claims the job, splits long documents into requests that fit the configured context window, and sends every part to Ollama. The expected JSON Schema is passed through Ollama's structured-output parameter rather than repeated in the document prompt.
4. Python verifies source quotations and reconciles dates, categories, line items, tax, gross, and breakfast amounts. A focused correction request is made only for validation issues that can benefit from another extraction. Truncated requests are not repeated unchanged.
5. The worker combines all validated documents into structured JSON. The browser polls the job while it runs and then loads the result.

Jobs are stored in Postgres. Workers claim them with database locks and renewable leases. An interrupted job can be reclaimed after the lease expires, by default after 20 minutes. It restarts from its document snapshot; three interrupted attempts mark it as failed.

## Services and troubleshooting

| Service | Address |
| --- | --- |
| API documentation | http://localhost:8000/docs |
| API readiness | http://localhost:8000/ready |
| Web interface | http://localhost:3000 |
| Postgres | localhost:5433 |
| S3 API | http://localhost:9000 |
| Storage console | http://localhost:9001 |

Storage credentials are in `.env`. Ollama is accessible only within the Docker network in the full-stack setup.

- **Docker connection error:** open Docker Desktop and wait until it is ready.
- **Job stays queued:** check the worker and model download logs.
- **Model download fails:** check the model name and Ollama version, then rerun `docker compose run --rm model-init` and `docker compose up -d worker`.
- **Job fails or takes too long:** run `docker compose logs --since=15m worker ollama`. Worker log lines include the job, document, pages, request duration, token counts, and Ollama completion reason. The browser console also records failed API requests and failed summary jobs.
- **PDF rejected:** check the page number in the error and confirm that its text can be selected.

The supplied configuration is for local development. Authentication is implemented, but all authenticated users currently share the same employee and trip workspace. Add organization and role-based access control before using one deployment for separate companies.

## Frontend structure

The React application is organized by responsibility:

- `src/pages`: complete screens and their workflow orchestration.
- `src/features`: authentication, employees, trips, documents, and summary UI.
- `src/shared/api`: Axios client and one API module per resource.
- `src/shared/ui`: reusable buttons, dialogs, status indicators, and empty states.
- `src/shared/types` and `src/shared/lib`: API contracts and formatting helpers.

React Query owns server state, polling, cache invalidation, and loading states. React Router keeps the selected employee and trip in the URL.

## Research and tests

`research/prototype.ipynb` compares models against synthetic English and Chinese invoices. Research prompts and its Markdown template remain separate from the application's extraction prompt and deterministic report renderer. Historical results are in `research/results/`.

`currency_exchange.py` is a standalone conversion utility. It is not connected to the reporting pipeline or an external rate provider.

Run the tests:

```bash
uv run pytest
uv run ruff check tera tests
cd frontend && npm run format:check && npm run lint && npm run build
```

To test with real Postgres and S3 services, start those containers and run:

```bash
TERA_INTEGRATION=1 uv run pytest tests/test_integration.py
```

The integration test uses an isolated database schema and storage bucket, removes its test data afterward, and substitutes a fixed model response. Model quality is evaluated separately.

## Manual receipt review

In **Ausgaben**, click the PDF filename to review the receipt. The dialog shows its
expenses, source quotations, automatic findings, and a PDF download. **Geprüft und
bestätigt** confirms all expenses from that receipt. **Ablehnen** excludes those
amounts from confirmed totals; rejected amounts remain visible separately.
**Prüfung zurücksetzen** restores the automatic assessment. Missing amounts or
currencies cannot be approved until extraction succeeds.

Decisions are stored for that particular report with the signed-in user's name,
time, and optional comment. Original extraction findings are preserved. JSON,
and category totals reflect the current decision and include its audit
history. A newly generated report requires its own review.

`PUT /summary-jobs/{job_id}/documents/{document_id}/review` accepts a `decision`
(`approved`, `rejected`, or `pending`) and an optional `comment`. The API locks the
report while updating it so concurrent reviews cannot overwrite each other.

Document context such as an explicitly fictional invoice or a draft appears under
**Beleghinweise**. These German notices are separate from extraction failures and
validation issues: they do not trigger a correction request, change the report
status, or remove amounts from confirmed totals. They remain visible after manual
review. The API exposes them as `notices` at report
and document level.
