"""Time the real pipeline on a private document snapshot without changing saved reports.

The input JSON is a list of objects with id, filename, sha256, page_count and pages.
Keep snapshots and outputs outside version control: they contain document text.
Run sequentially for each model so competing requests do not distort the timings.
"""

import argparse
import json
import logging
import time
from pathlib import Path
from types import SimpleNamespace

from tera.chunking import chunk_pages
from tera.config import Settings
from tera.exchange_rates import attach_rate
from tera.llm import OllamaExtractor
from tera.localization import localize_record
from tera.processing import process_document
from tera.prompts import PROMPT_VERSION
from tera.reporting import make_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--match", help="Only filenames containing this text")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    settings = Settings(_env_file=None, ollama_model=args.model)
    documents = json.loads(args.snapshot.read_text())
    if args.match:
        documents = [d for d in documents if args.match.casefold() in d["filename"].casefold()]
    if not documents:
        parser.error("No matching documents")
    started = time.perf_counter()
    records, timings = [], []
    rate_cache = {}
    for index, row in enumerate(documents, 1):
        document_started = time.perf_counter()
        document = SimpleNamespace(**row)
        record = process_document(
            document,
            chunk_pages(document.id, document.pages, settings),
            OllamaExtractor(settings),
            settings,
            lambda **_: None,
        )
        extracted = time.perf_counter()
        localize_record(record, settings)
        localized = time.perf_counter()
        attach_rate(record, rate_cache)
        finished = time.perf_counter()
        records.append(record)
        timing = {
            "document_id": document.id,
            "extraction_seconds": round(extracted - document_started, 2),
            "translation_seconds": round(localized - extracted, 2),
            "exchange_rate_seconds": round(finished - localized, 2),
            "total_seconds": round(finished - document_started, 2),
        }
        timings.append(timing)
        report = make_report(records, args.model, PROMPT_VERSION)
        args.output.write_text(
            json.dumps(
                {
                    "seconds": round(time.perf_counter() - started, 2),
                    "timings": timings,
                    "complete": index == len(documents),
                    "report": report,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print(
            json.dumps(
                {
                    "document": index,
                    "of": len(documents),
                    **timing,
                    "warnings": len(record["warnings"]),
                    "failed": record["extraction_failed"],
                }
            ),
            flush=True,
        )
    print(f"Report finished in {time.perf_counter() - started:.2f} seconds", flush=True)


if __name__ == "__main__":
    main()
