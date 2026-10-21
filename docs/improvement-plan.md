# Report usability improvement plan

Captured on 2026-10-20 after a complex multi-document travel test. This file records the goals; implementation status is summarized below.

## Goal

Reduce the effort needed to verify a trip. Preserve detailed evidence internally while showing a compact report with actionable issues.

## Priorities

1. **Compact expenses:** show one row per service, with fees and other components expandable. Keep meaningful category splits, such as accommodation and breakfast. Show exchange-rate details once per expense rather than once per component.
2. **Actionable validation:** aggregate related issues into a specific user action; keep technical codes in diagnostics. Check evidence across the assembled document, not only within isolated fragments. A repeated value alone is not a discrepancy. Do not hide unresolved material errors.
3. **Reliable localization:** retain original provider names and descriptions. Translate foreign text when needed and show original/translation together. Avoid replacing readable text with generic placeholders or retranslating deterministic German validation messages.
4. **Document roles:** distinguish invoices/receipts, payment confirmations, bookings/tickets, supporting explanations and unreadable documents. Apply role-appropriate checks; do not treat every PDF as an additional expense. A debit in a bank statement is not automatically a refund.
5. **Related documents:** represent a service once with multiple supporting documents. Match using transaction or trip identifiers, time, route, amounts and other evidence. Ambiguous matches need review; filenames or dates alone are insufficient. Prevent double counting invoice/receipt/payment combinations.
6. **Input preparation:** inspect actual prompt sizes and fragmentation. Preserve useful document context and avoid splitting small documents unnecessarily. Assess selective OCR for scanned pages or unusable text layers; do not assume OCR improves every digital PDF.
7. **Model comparison:** compare the current 9B model with a larger candidate on the same test documents after the main pipeline issues are addressed. Record extraction accuracy, evidence quality, duplicate handling, review effort, failures and latency. A larger model cannot fix report layout or accounting logic by itself.

## Acceptance direction

A reviewer can quickly identify the trip total, genuine unresolved problems and supporting source text. Evaluation must include representative real model outputs; passing unit tests does not establish usability or extraction quality.

## Implementation status

Implemented: compact per-document/category expenses, role-specific handling, verified-reference
linking and conservative duplicate candidates, actionable review summaries, source rows and
quotation recovery, safer correction passes, German source translations, persisted generation
timing, and a repeatable private-data benchmark. Existing PDFs are re-read on new reports when
their layout version is old. Supporting documents remain accessible without adding expenses.

Still limited: general mixed-category itemization, missing or misidentified providers/dates,
ambiguous document relationships, complex page layouts, and model translation reliability.
Source translations and unresolved relationships still require targeted user checks. Larger
models need a broader controlled comparison before changing the default. OCR remains deferred
at the user's request.
