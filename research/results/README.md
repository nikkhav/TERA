# Model comparison

Latest run: **2026-09-21, 17:16:56 UTC**. All three models completed both extraction tests and a combined German summary using the current research prompt and Markdown template.

The `.md` summaries are unedited model responses. The observations below are a manual review. These are research results, not outputs of the application's Python report renderer.

## Run configuration

- Models: `gemma3:12b`, `qwen3:14b`, `qwen3.5:9b`.
- Input: one synthetic English hotel invoice and one synthetic Chinese hotel invoice.
- Temperature: 0; context window: 8192 tokens. Thinking was disabled for both Qwen models.
- Extraction: the research schema is supplied through Ollama's `format` parameter.
- Summary: both document texts are supplied directly, without an output schema or Python calculations.

[Evaluation data](evaluation.json) contains raw extraction responses, scores, timings, completion time, and hashes of the prompts, template, and input PDFs. Executed tables and summaries are also saved in [the notebook](../prototype.ipynb).

## Field extraction

| Model | English invoice | Chinese invoice |
| --- | --- | --- |
| Gemma 3 12B | 13/14 (92.9%) | 14/14 (100%) |
| Qwen 3 14B | 13/14 (92.9%) | 14/14 (100%) |
| Qwen 3.5 9B | 12/14 (85.7%) | 14/14 (100%) |

All three models returned **EUR 60.00 net** for the English breakfast field, while the reference expects **EUR 71.40 gross**. The field name does not specify net versus gross, so this exposes an ambiguous evaluation contract rather than an inability to read the amount.

Qwen 3.5's additional mismatch is address formatting: it returned a newline between the street and city instead of the reference's comma and space. The address content is correct. Its lower strict-match score therefore does not establish worse factual extraction.

## Summary review

| Model | Overall totals | Hotel and breakfast breakdown | Language and format |
| --- | --- | --- | --- |
| [Gemma 3 12B](summary_gemma3_12b_de.md) | Displays EUR 712.60 and CNY 2220.00, but its EUR detail tables do not reconcile | Uses net EUR charges; returns `Ja` instead of amounts with breakfast and leaves both costs without breakfast unknown | Keeps the seven sections, but leaves English/Chinese descriptions and decimal points |
| [Qwen 3 14B](summary_qwen3_14b_de.md) | EUR 670.60 is missing EUR 42.00 city tax; CNY 2220.00 is correct | Correct gross breakfast and costs without breakfast for both invoices | Clearest German in this run; decimal commas; omits zero-value categories and uses non-ISO service dates |
| [Qwen 3.5 9B](summary_qwen3.5_9b_de.md) | EUR 673.40 is missing EUR 39.20 accommodation VAT; CNY total is correct but categories double-count breakfast | Correct numeric breakfast deductions, with contradictory classifications elsewhere | Keeps the seven sections, but mixes languages, uses decimal points, changes category order and source identifiers |

### Gemma 3 12B

- The EUR expense rows sum to **662.00**: accommodation 560.00, breakfast 60.00, and city tax 42.00.
- The category table instead lists Hotel 602.00, Verpflegung 60.00, and Sonstige Ausgaben 42.00, totaling **704.00**. The city tax appears in both Hotel's amount and Sonstige Ausgaben.
- The displayed grand total is **712.60**. A note acknowledges a discrepancy, but the report still says zero documents need review and labels the amounts confirmed.
- Both `Mit Frühstück` cells contain `Ja`, and both `Ohne Frühstück` cells are unknown despite available amounts.
- Several review notes introduce unnecessary uncertainty about the Chinese invoice, whose tax and breakfast amounts are explicit.

### Qwen 3 14B

- The English expense table omits city tax, so its daily and overall totals are **670.60** instead of **712.60**.
- The accommodation section separately gives the correct **712.60 − 71.40 = 641.20 EUR**. The discrepancy between sections is not flagged.
- The Chinese amounts reconcile to **2220.00 CNY**, with **180.00 CNY** breakfast and **2040.00 CNY** excluding breakfast.
- German descriptions are readable. Remaining format issues include omitted zero-value categories, service dates written as `DD.MM.YYYY`, and currency ordering.

### Qwen 3.5 9B

- Hotel is **602.00 EUR**, combining net accommodation of 560.00 with city tax of 42.00. Adding gross breakfast of 71.40 gives **673.40 EUR**, omitting accommodation VAT of 39.20.
- The Chinese expense row assigns the entire **2220.00 CNY** to Hotel as a breakfast bundle. The category table then adds **180.00 CNY** under Verpflegung, making its category sum **2400.00 CNY** while its grand total remains 2220.00.
- The accommodation table gives the correct deductions **641.20 EUR** and **2040.00 CNY**, but incorrectly describes the latter as net accommodation.
- Source cells use invoice numbers instead of the supplied PDF document identifiers. Descriptions retain English and Chinese text, and the report flags none of its contradictions.

## Reference amounts

Hotel category totals below include lodging taxes and exclude separately priced breakfast.

| Currency | Invoice total | Hotel | Verpflegung / breakfast | Flugreisen | Sonstige Ausgaben |
| --- | ---: | ---: | ---: | ---: | ---: |
| EUR | 712.60 | 641.20 | 71.40 | 0.00 | 0.00 |
| CNY | 2220.00 | 2040.00 | 180.00 | 0.00 | 0.00 |

The English Hotel amount includes EUR 42.00 city tax. Its room-only gross amount is EUR 599.20, and its stated nightly net rate is EUR 140.00. The Chinese amounts already include VAT. Currencies must remain separate.

## Interpretation

No model produced a fully consistent direct Markdown report in this run. Qwen 3 14B had the clearest German, but dropped a charge. Qwen 3.5 9B did not demonstrate an improvement in summary reliability on these fixtures, despite extracting the underlying receipt fields comparably once the address-format mismatch is distinguished from factual errors.

This is one run on two synthetic invoices. Extraction accuracy, arithmetic consistency, categorization, and language quality measure different things; none should substitute for the others. The application calculates totals and renders Markdown in Python, so these direct-generation failures are not measurements of that application's report renderer.
