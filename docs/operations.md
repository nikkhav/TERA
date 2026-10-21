# Operating TERA

Start with the commands in the [README](../README.md). Run `make dev-setup` again after database migrations. Local development uses `.env.development`, SQLite and `.local/documents`. Do not run the Docker API and local API together: both use port 8000.

## Configuration

The example environment files list available settings. The most useful are:

| Setting | Purpose |
| --- | --- |
| `OLLAMA_MODEL` | Model to use for new reports |
| `OLLAMA_URL` | Local model server address |
| `OLLAMA_THINK` | Whether to request model reasoning; default false |
| `MODEL_CONTEXT_TOKENS` | Total model context window |
| `MODEL_OUTPUT_TOKENS` | Reserved response budget |
| `MODEL_TIMEOUT_SECONDS` | Maximum time per model request |
| `RECEIPT_RECHECK_ENABLED` | Allow one correction pass after validation issues |
| `AUTH_ALLOW_REGISTRATION` | Allow new accounts |
| `AUTH_SECRET_KEY` | Token signing secret |

Finish active jobs before changing the model. For Docker, update `.env`, run `docker compose run --rm model-init`, then `docker compose up -d --force-recreate api worker`. Host Ollama users install models directly instead. For Linux NVIDIA GPU support use `compose.gpu.yaml` alongside `compose.yaml`.

Before a production deployment, set `APP_ENVIRONMENT=production` and a unique signing secret of at least 32 bytes. All accounts share one employee/trip workspace. Separate organizations and roles are not implemented.

## Reports and source locations

Uploads accept readable PDFs with a text layer (default limits: 20 MB and 200 pages). Scanned pages without text and password-protected PDFs are rejected. Original files remain available to download.

New uploads store visual text rows, coordinates and stable row IDs. Chunks preserve complete rows where they fit; a row larger than the input budget must be split. Evidence includes page, quotation and, when uniquely resolved, row ID and character offsets into the extracted page text. Offsets are calculated and checked by Python. Repeated unanchored quotations are not treated as proof that two items are identical. New reports re-read original PDFs when the stored layout version is older, so existing uploads benefit without re-uploading. Old reports retain their original quotations.

Python verifies quotations, printed monetary values and arithmetic. Selected payment/subtotal labels are rejected as evidence for an invoice total; this is a limited multilingual check, not a complete interpretation of every possible receipt. Validation runs after the document fragments have been assembled. New layout-based input requires support for the invoice date and currency; currency codes and unambiguous symbols may also be checked in the original document text. Missing optional provider information and absent itemization alone do not invalidate a printed total. Missing or unsupported evidence triggers review, rather than silently discarding the claimed value. Printed tax/net amounts may be used to derive a missing gross amount.

The progress bar counts documents that have finished extraction, checks, localization and currency lookup, including documents that finished with errors. The total is fixed by the job snapshot. It measures completed documents, not remaining time; individual documents can take different amounts of time.

Requests use a conservative UTF-8 byte budget, with space reserved for output and one correction request. Truncated responses are flagged rather than repeated unchanged. Jobs retain their document snapshot, model and prompt version. Adding a document marks an existing report as stale; generate a new report to include it.

Use the trash button next to a document to delete it. Deletion removes the original PDF and its database record; old reports remain available but become stale, and their deleted PDF can no longer be downloaded. Generate a new report to update expenses and totals. Deletion is blocked while the trip has a queued or running report.

Review and correction history belongs to the specific report. A new report needs its own review. Confirmed, pending and rejected amounts remain separate. Missing conversions are not counted as zero. An automatic `completed` status is not reimbursement approval.

Historical exchange rates come from the Bankenverband calculator's public endpoint. They use the invoice date and are saved with the report. The endpoint has no documented third-party availability guarantee. No personal data is sent. German localization targets foreign descriptions and source quotations, rather than retranslating deterministic German validation messages. Original names and descriptions are retained on failure. Foreign source quotes can show a separate German translation; numeric changes in that translation are rejected. Translation failures remain visible.

## Troubleshooting

| Problem | Check |
| --- | --- |
| Docker cannot connect | Start Docker Desktop |
| Queued job | Worker and model-init logs; model availability |
| Slow or failed extraction | Worker logs: request duration, token counts and completion reason |
| Rejected PDF | Selectable text on every page; password and file limits |
| Unconverted currency | Invoice date, supported currency and provider availability |
| Interrupted worker | Jobs can be reclaimed after the lease expires (default 20 minutes) |

Docker logs: `docker compose logs --since=15m worker ollama`. With host Ollama, inspect the host model server instead of the container. API readiness: [localhost:8000/ready](http://localhost:8000/ready). API schema: [localhost:8000/docs](http://localhost:8000/docs).

Docker storage console: port 9001; S3: port 9000; Postgres: port 5433. Credentials are in `.env`. Stop services with `docker compose stop`; restart with `docker compose up -d`.

## Compact multi-document review

The main table groups expense components by document and category. Detailed line items and original/translated labels remain in the review dialog. Accommodation and breakfast remain separate categories. Expense dates prefer the service date; currency conversion continues to use the invoice date.

`document_kind` distinguishes invoice/receipt (including priced tickets), payment, booking-only confirmation, supporting document and unknown. Supporting documents remain visible and downloadable without becoming extra expenses. Correct a wrong role using **Bearbeiten → Dokumenttyp**.

`tera/document_links.py` links complementary invoice/receipt records when a shared service reference appears in verified source quotations and their currency and total agree. One record supplies the expense; additional records remain accessible as supporting evidence. Conflicting totals or weaker date/provider/amount matches require review and are not merged automatically. The user can correct the role/reference or reject a repeated expense document. Matching does not rely on filenames alone.

Review lists show grouped actions; detailed warnings remain expandable. Technical feedback codes are not presented as user-facing findings. Existing reports keep their saved output: generate a new report to apply these processing changes.

New defaults are 16384 context tokens and 4096 output tokens. Existing environment files can override these: update `MODEL_CONTEXT_TOKENS` and `MODEL_OUTPUT_TOKENS` if they still contain the older 8192/2048 values. Larger limits require more memory; compare actual latency and memory usage with the selected model.

The UI displays queue waiting time, then elapsed generation time, and the final duration.
Generation time includes extraction, correction attempts, translation and exchange rates.
The first worker start and final completion timestamps are persisted; worker restarts do not
reset the displayed elapsed time. Historical jobs without a start timestamp show total time
including the queue. Apply database migrations before restarting the API and worker.

## Reviewing related receipts and original PDFs

The review tab groups a possible repeated expense into one task. **Belege vergleichen**
shows dates, providers, routes and amounts with a **PDF ansehen** link under each document.
PDF links open in separate tabs. Select the document
whose amount should supply the expense and choose **Eine Ausgabe, … Belege**, or keep
**Getrennte Ausgaben**. The decision is recorded with the reviewer and timestamp and can be
reset. Combining documents does not approve other open findings or remove the originals.
A weaker possible match remains unresolved until a person chooses; no totals change merely
because the UI groups rows. Different amounts and category splits remain visible separately.

The expense list shows EUR amounts first, the original currency underneath, and compact
statuses. Rates, source details and full filenames are available in review. Original PDFs
open through **PDF ansehen** in a dedicated full-page tab, loading through the authenticated
API only after that tab opens. Closing the review dialog does not close the PDF. The tab can
be reloaded and displays loading, authentication and storage errors explicitly. A direct-open
fallback is provided for browsers without an embedded PDF viewer. The download button remains
available. PDFs are no longer loaded or embedded in the review/comparison modals.

**Transport** covers taxis, trains, buses and public transit; flights remain **Flugreisen**.
New model extraction and the correction form support this category. Existing reports retain
their saved category until corrected or regenerated. Relationship choices are stored in the
report JSON and do not require a new database migration.

A missing model citation is distinct from a conflicting value. Ride receipts can recover a
missing issue-date citation from a standalone date heading on the first page when the
existing extracted date matches and other numeric dates do not contradict it. The original
row is retained as evidence with a provenance notice; no date or amount is invented or
changed. Explicitly labeled invoice dates still use their labels. Resolving a document
relationship also refreshes this specific missing-date evidence on existing report records,
without a model call. Other findings and review decisions are retained. The UI identifies
unsupported dates, currencies and document totals individually instead of merging them into
a generic monetary-evidence warning.
