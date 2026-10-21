# TERA — Travel Expense Review Assistant

TERA helps employees review travel receipts. Upload PDFs for a trip, generate a German report, and check expenses, source quotations and possible inconsistencies. A person makes the final reimbursement decision.

The application uses React, FastAPI and a local Ollama model. Development stores data in SQLite and a local folder; Docker uses Postgres and S3-compatible storage.

## Run locally

Requires Python 3.11+, uv, Node.js/npm and [Ollama](https://ollama.com/download).

```bash
uv sync --locked
cd frontend
npm ci
cd ..
make dev-setup
```

Start the Ollama app, or run the server in a separate terminal and leave it running:

```bash
ollama serve
```

If the Ollama app is already running, skip `ollama serve`. Check `OLLAMA_MODEL` in `.env.development` and download that model. For the default configuration:

```bash
ollama pull qwen3.5:9b
```

Use the exact model name from your settings if you changed it. Check that the server responds and the model appears in the list:

```bash
curl http://localhost:11434/api/tags
```

Keep Ollama running while generating reports. Start each of these commands in its own terminal, from the project folder:

```bash
make dev-api
make dev-worker
make dev-web
```

Open [localhost:5173](http://localhost:5173), create an account, then:

1. Add an employee and a trip.
2. Upload receipts (one receipt per PDF, with selectable text).
3. Choose **Auswertung erstellen**. The progress bar counts completed documents; the timer shows elapsed processing time.
4. Compare the report with the PDFs. Use **Bearbeiten** to correct values or **Prüfen / bestätigen** to record a decision.

After adding or removing PDFs, choose **Auswertung aktualisieren**. Unchanged documents reuse their results and manual decisions; only new or previously failed documents are analyzed. Links, duplicates and totals are checked across the full set again. Changed processing settings or code require a fresh analysis; older reports need one full run to enable reuse. **Alle Belege neu analysieren** deliberately starts over without carrying manual decisions into the new report.

## Run with Docker

Copy `.env.example` to `.env` if it does not exist, then run:

```bash
docker compose up --build -d
```

Open [localhost:3000](http://localhost:3000). First startup downloads the configured model and can take several minutes. Check `docker compose logs -f model-init worker` if jobs stay queued.

On Apple Silicon, use host Ollama for GPU acceleration. Start Ollama and download the model as described above, using `OLLAMA_MODEL` from `.env` for this Docker setup:

```bash
docker compose -f compose.yaml -f compose.host-ollama.yaml up --build -d
```

`docker compose stop` preserves data. **`docker compose down -v` deletes stored data and model files.**

## How it works

PDF → text rows with source locations → bounded model requests → document-level evidence and arithmetic checks → compact report.

The model extracts facts and identifies the document role; Python combines results and calculates totals. Payment confirmations and supporting documents stay accessible without being added as extra expenses. Ordinary single-category receipts use one total; accommodation and explicitly priced breakfast can appear separately. Unresolved issues stay visible for review. Foreign expenses retain their original currency and show EUR conversions when a historical rate is available. Only currency codes, a date and amount 1 are sent to the exchange-rate provider; document text stays local.

## Checks and further reading

```bash
make test
```

- [Setup, configuration and troubleshooting](docs/operations.md)
- [User testing checklist and current limits](docs/testing.md)
- [API documentation](http://localhost:8000/docs)

Main code: `tera/pdf.py` and `chunking.py` prepare input; `llm.py` checks extraction evidence; `reconciliation.py` checks arithmetic; `reporting.py` builds reports; `api.py` and `worker.py` run the workflow. The React interface is in `frontend/src`. Model experiments are in `research/`.
