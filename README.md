# TERA — Travel Expense Review Assistant

TERA organizes PDF receipts by employee and trip, then generates a German expense report. The backend uses FastAPI, Postgres, S3-compatible storage, and Ollama.

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

This starts Postgres, file storage, Ollama, the API, and a worker. Setup services create the database tables and storage bucket, and download the selected model. The worker starts after the download succeeds. The first startup can take a while.

Check progress:

```bash
docker compose ps -a
docker compose logs -f model-init worker
```

Model files, uploaded PDFs, and the database are stored in persistent Docker volumes. Existing model files are reused on subsequent starts. Model files installed in a host Ollama installation are separate from the Docker volume.

### 3. Open the API

Open [localhost:8000/docs](http://localhost:8000/docs). You can try every operation there without a frontend.

Use **Try it out**, fill in the fields, and click **Execute**:

1. Create an employee with `POST /employees`, for example `{"name": "Alex Morgan"}`. Copy the returned `id`.
2. Create a trip with `POST /employees/{employee_id}/trips`, for example `{"name": "Berlin, September 2026"}`. Copy the trip `id`.
3. Upload a PDF with `POST /trips/{trip_id}/documents`. Repeat for each receipt. Sample files are in `research/data/`.
4. Start a report with `POST /trips/{trip_id}/summaries`. Copy the job `id`.
5. Check `GET /summary-jobs/{job_id}` until processing finishes.
6. Get the report from `GET /summary-jobs/{job_id}/result`, or download Markdown from `/summary-jobs/{job_id}/markdown`.

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

`OLLAMA_THINK` is an optional request setting. Leave it unset if the selected model does not support it. Context size, output budget, and timeout are also configured in `.env`. `OLLAMA_IMAGE` selects the Ollama container version; use a tested version or image digest for a deployment.

The default Docker configuration runs inference on CPU. On a Linux server with an NVIDIA GPU and NVIDIA Container Toolkit installed, use:

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up --build -d
```

See the official [Ollama Docker instructions](https://docs.ollama.com/docker) for GPU setup. On Apple Silicon, running Ollama directly on macOS is preferable for GPU acceleration; use the local development setup below.

## Local development

Use Python 3.11 or newer, `uv`, and a running local Ollama. Keep Postgres and file storage in Docker:

```bash
uv sync --locked
docker compose up -d postgres s3
uv run alembic upgrade head
uv run python -m tera.init_storage
```

Download the model named in `.env` using `ollama pull <model>`. Then start the API and worker in separate terminals:

```bash
uv run uvicorn tera.api:app --reload
```

```bash
uv run python -m tera.worker
```

Both processes must be running. Local processes use `OLLAMA_URL` from `.env`; Docker services use the internal Ollama address. If the full Docker stack is already running, stop its `api` and `worker` before starting local copies.

## API and report data

`GET /summary-jobs/{id}/result` returns structured JSON and a rendered `markdown` field:

- `coverage`: document counts and processing failures.
- `documents`: extracted facts, source quotations, and review notes.
- `expenses`: dated expense rows with categories and source pages.
- `totals`: totals by date, category, and currency.
- `accommodation`: hotel and breakfast amounts.
- `warnings`: items requiring review.

Amounts are decimal strings such as `"712.60"`; missing values are `null`. A frontend can use JSON for tables and filters, and Markdown for export. Response types are documented in `/docs` and `/openapi.json`.

Jobs have these states: `queued`, `running`, `completed`, `needs_review`, or `failed`. Progress is available through `completed_chunks` and `total_chunks`. Partial results identify failed documents explicitly. Completion is not an approval for reimbursement.

Generating a report captures the documents currently in the trip. Repeated requests return the active job instead of creating duplicates. Uploading another document makes an existing report `is_stale: true`; generate a new report to include it. Lists support `limit` and `offset`.

## Document processing

Uploads must be readable PDFs with selectable text. Default limits are 20 MB and 200 pages per file. Each PDF should contain one receipt or invoice, which can span multiple pages.

The worker splits document text into bounded requests while retaining page references. It uses a conservative UTF-8 byte budget with space reserved for instructions and output, rather than a model-specific tokenizer. Failed or truncated responses become review items.

The model extracts facts from each part. Python validates references, merges consistent facts, calculates totals using `Decimal`, and renders Markdown in a fixed layout. Conflicting values and suspected duplicates require review; they are excluded from confirmed totals. Each currency is kept separate. Separate breakfast charges are assigned to Verpflegung without being counted twice.

Jobs are stored in Postgres. Workers claim them with database locks and renewable leases. An interrupted job can be reclaimed after the lease expires, by default after 20 minutes. It restarts from its document snapshot; three interrupted attempts mark it as failed.

## Services and troubleshooting

| Service | Address |
| --- | --- |
| API documentation | http://localhost:8000/docs |
| API readiness | http://localhost:8000/ready |
| Postgres | localhost:5433 |
| S3 API | http://localhost:9000 |
| Storage console | http://localhost:9001 |

Storage credentials are in `.env`. Ollama is accessible only within the Docker network in the full-stack setup.

- **Docker connection error:** open Docker Desktop and wait until it is ready.
- **Job stays queued:** check the worker and model download logs.
- **Model download fails:** check the model name and Ollama version, then rerun `docker compose run --rm model-init` and `docker compose up -d worker`.
- **Job fails:** check `docker compose logs worker`, resolve the error, and create a new job.
- **PDF rejected:** check the page number in the error and confirm that its text can be selected.

The supplied configuration is for local development. Authentication and employee-level access control are not implemented. Add them and replace development credentials before making the API available to other users.

## Research and tests

`research/prototype.ipynb` compares models against synthetic English and Chinese invoices. Research prompts and its Markdown template remain separate from the application's extraction prompt and deterministic report renderer. Historical results are in `research/results/`.

`currency_exchange.py` is a standalone conversion utility. It is not connected to the reporting pipeline or an external rate provider.

Run the tests:

```bash
uv run pytest
uv run ruff check tera tests/test_api_pipeline.py tests/test_llm.py tests/test_integration.py
```

To test with real Postgres and S3 services, start those containers and run:

```bash
TERA_INTEGRATION=1 uv run pytest tests/test_integration.py
```

The integration test uses an isolated database schema and storage bucket, removes its test data afterward, and substitutes a fixed model response. Model quality is evaluated separately.
