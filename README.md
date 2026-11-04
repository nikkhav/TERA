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

## Password recovery for administrators

An administrator with access to the server creates a recovery link. The user then
chooses a new password in the browser. Email delivery is handled manually.

1. Open a terminal on the server and go to the TERA project directory.
2. Use the account's registered email and the address where users open TERA:

   ```bash
   docker compose exec api python -m tera.password_reset person@example.org --base-url https://tera.example.org
   ```

   Replace `person@example.org` and `https://tera.example.org` with the actual values.
   For local Docker testing, use `--base-url http://localhost:3000`.
   With host Ollama, use the same Compose files as at startup:

   ```bash
   docker compose -f compose.yaml -f compose.host-ollama.yaml exec api python -m tera.password_reset person@example.org --base-url http://localhost:3000
   ```

3. Copy the complete printed link and privately give it to the verified account owner.
   Anyone who has this link can set a new password for that account.
4. The user opens the link, enters and confirms a new password of 12–128 characters,
   then signs in with their email and new password.

The link works once and expires after 30 minutes. Add `--expires-minutes 60` to allow
one hour. To replace an expired or lost link, run the command again. Each new link
invalidates the previous link for that account. Existing sessions are revoked when
the user successfully sets the new password.

If the command reports `Active user not found.`, check the registered email and
whether the account is active. If a link is invalid or expired, create a new one.
The login page's **Passwort vergessen?** message directs users to the administrator.

The Docker command issues the link. The browser submits the token and new password
to `POST /auth/reset-password`. Successful redemption returns HTTP 204. Issuing links
requires server access through the command above. See
[operations](docs/operations.md#password-recovery-without-email) for local development details.

## How it works

PDF → text rows with source locations → bounded model requests → document-level evidence and arithmetic checks → compact report.

The model extracts facts and identifies the document role; Python combines results and calculates totals. Payment confirmations and supporting documents stay accessible without being added as extra expenses. Ordinary single-category receipts use one total; accommodation and explicitly priced breakfast can appear separately. Unresolved issues stay visible for review. Foreign expenses retain their original currency and show EUR conversions when a historical rate is available. Only currency codes, a date and amount 1 are sent to the exchange-rate provider; document text stays local.

## Checks and further reading

```bash
make check
```

- [Setup, configuration and troubleshooting](docs/operations.md)
- [API documentation](http://localhost:8000/docs)

Main code: `tera/pdf.py` and `chunking.py` prepare input; `llm.py` checks extraction evidence; `reconciliation.py` checks arithmetic; `reporting.py` builds reports; `api.py` and `worker.py` run the workflow. The React interface is in `frontend/src`.
