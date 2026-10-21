# Preparing a user test

Use a separate test account and trip. The workspace is shared by all accounts. Keep original PDFs available so participants can compare every result.

## Before the session

1. Run `make test`. The normal API tests use SQLite, in-memory storage and fixed model responses.
2. For Docker deployments, start Postgres/S3 and run `TERA_INTEGRATION=1 uv run pytest tests/test_integration.py`. This uses isolated test data and a fixed extraction response.
3. Start the API, worker, frontend and the configured Ollama model. Confirm API readiness and that the model is installed.
4. Upload a representative receipt, generate a report and record processing time. Check source quotations, totals, categories, German text and EUR conversion against the original.
5. Repeat with representative foreign-language documents and a long document. Automated tests do not establish real model quality.

## Participant workflow

- Create an employee and trip; upload multiple receipts.
- Generate a report and follow progress to completion.
- Find an expense, its source quotation and the original PDF.
- Explain one flagged issue; correct a value and confirm the correction.
- Reject an expense document and verify that excluded totals update.
- Add a receipt; check the stale-report indication and regenerate.
- Sign out and back in; check that the saved review is still available.

Record completion, unclear steps, incorrect findings, missing findings and processing time. Do not treat an extracted amount or automatic status as an approval decision.

## Important cases

| Case | Expected behavior |
| --- | --- |
| Two different lines both cost 20.00 | Both remain visible |
| A quotation points to the wrong row | Evidence fails verification; review is required |
| Deposit 100, invoice total 200 | Deposit must not support total 100 |
| Missing or unsupported date/currency evidence | Review is required for new layout input |
| Invoice without a VAT breakdown | Printed gross total remains usable |
| No selectable text | Upload identifies the affected page |
| Model unavailable or response truncated | Visible failure/review state, no invented totals |
| Duplicate invoice | Possible duplicate warning; excluded from automatic confirmed totals |

## Current limits

Row reconstruction uses word coordinates and accounts for different font sizes on one
visual line. Complex columns, rotated text and tables spanning pages still need checking.
Table headers and currency context are not automatically repeated across chunks. A shared
verified service reference can link complementary invoice/receipt records; weaker matches
require a person to decide. Automatic item extraction currently targets explicit breakfast
splits; other single-category expenses use their printed total. General mixed-category
invoices still need manual checking. Date/currency and amount-label checks are deliberately
limited and do not prove every possible semantic interpretation. OCR is not implemented.

A successful automated suite establishes tested software behavior, not model accuracy.
Real PDFs must also be checked against their originals.

## Checks on 2026-10-20

108 backend tests passed, including the Postgres/S3 integration test with isolated test data.
Ruff, frontend formatting, ESLint, TypeScript and the production build passed.
Browser checks used a separate local database: login, compact review, final duration,
running progress and elapsed time after reload were verified. User reports were not modified.

Live extraction used existing document text and then original PDFs re-extracted with the
updated layout. Both Qwen 3.5 9B and 27B were exercised. A larger model did not by itself fix
split source rows. See the timing results below for scope and limitations.

## Multi-document regression checks

The compact-report checks cover a taxi fare with fee components, total-only receipts,
payment statements that must not add expenses, invoice/receipt linking with verified
references, conflicting amounts and distinct services, document-wide evidence,
recheck degradation, source-row quotation recovery, and translations that retain
original values. Technical feedback is collapsed into actions while arithmetic
mismatches stay explicit. These checks do not establish model accuracy on every PDF.

## Repeatable timing

Use a private JSON snapshot with `id`, `filename`, `sha256`, `page_count` and `pages` for
each document. Run models sequentially on the same snapshot:

```bash
python -m research.benchmark /tmp/private-documents.json --model qwen3.5:9b --output /tmp/report-9b.json
python -m research.benchmark /tmp/private-documents.json --model qwen3.5:27b --output /tmp/report-27b.json
```

The output records extraction (including correction), translation, currency lookup and total
wall time, plus the generated report. Check `complete` before comparing runs. Output includes
private document data and must not be committed. Timings include model loading and provider
latency; do not run competing model jobs during comparisons. The CLI does not change saved
application reports or review decisions.

## Observed timings and outcomes

| Run | Scope | Elapsed |
| --- | --- | --- |
| Previously saved 9B report | 15 documents; includes unknown queue time | 21 min 18 sec |
| New 9B full pipeline | Same 15 original PDFs, refreshed layout, extraction/correction, translation and rates | 11 min 25 sec |
| Post-fix 9B repeat | Five selected difficult documents, full pipeline | 3 min 25 sec |

The full run completed all 15 documents without extraction failures. Its time comprised
630.9 seconds extraction/correction, 17.4 seconds translation and 37.2 seconds currency lookup.
Additional date, translation and validation fixes were made during that run, then evaluated
on the five-document repeat. This is not a controlled speedup claim: queue time, model loading,
provider latency and the exact code revision differed. The full dataset has not yet been
rerun with every final change.

The repeat recovered the selected receipt totals and dates, translated Chinese evidence,
and detected a matching invoice/receipt pair as a possible duplicate requiring joint review.
A plain ticket-validity note was still misclassified as a warning; a subsequent regression
fix retains this as informational text while preserving conflicting-date warnings.

27B was tried on three documents before the final layout/validation fixes. Extraction with
correction took approximately 140, 122 and 80 seconds. It still could not verify the split
Chinese total row, so these results do not justify switching the default model. A fair final
model comparison requires the same final code, documents and independently checked outcomes.

Remaining manual checks include uncertain invoice/receipt relationships, missing receipt
dates, provider identification and any failed translations or EUR conversions. Automated
status is not reimbursement approval. Real document text and report snapshots are not stored
in this repository.

A final provider-identification check on another ride receipt completed in 29.83 seconds.
The revised prompt correctly identified the platform rather than the driver and extracted
the printed total and receipt date without validation warnings. The currency provider timed
out after 10 seconds; the report retained the original currency amount and an explicit
missing-conversion message. All live document results passed the API response schema.

## Compact review and PDF preview regression checks (2026-10-21)

API tests check authenticated inline PDFs, original-byte preservation, download compatibility,
relationship decisions, saved history, changing a decision, reset, and rejecting duplicate or
foreign document IDs. Financial totals are checked after combining and separating documents.
Frontend grouping tests check one task for a pair, preservation of other findings, distinct
amounts/category splits, resolved separate expenses and non-mutation of underlying totals.
Run these through `npm test` in `frontend` or the top-level `make test`.

Manual browser checks: open **PDF ansehen** under each document, read it in a separate tab,
close the review dialog and reload the PDF tab. Compare the documents, select the
primary amount source, combine/separate/reset, and check the resulting totals after reload.
Also check a deleted original and a browser without an embedded PDF viewer. These additions
were checked by API tests and frontend compilation; native PDF rendering was not visually
verified in a browser during this update.
