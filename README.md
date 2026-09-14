# TERA — Travel Expense Review Assistant

> **Status: Work in Progress (WIP)**
>
> TERA is a bachelor thesis research prototype. Its architecture, data schema, processing pipeline, and model responsibilities may change as the research progresses.

## Research and Prototyping Phase

The first phase evaluates the core document-processing approach in Jupyter notebooks. The experiments focus on:

- comparing open-weight language models for extracting information from travel expense documents;
- evaluating libraries for extracting text from PDF files;
- defining and refining the target structured output format.

The experiments are located in the `research/` directory.

## Structured Output

Extracted document information is converted into JSON. The schema is still under development and will evolve as additional document types, validation rules, and reimbursement requirements are examined.

## PDF Processing Strategy

When a PDF is uploaded, the system first determines whether it contains usable machine-readable text.

1. Attempt direct text extraction with PyMuPDF.
2. Evaluate whether the extracted text is sufficient for further processing.
3. If the text is usable, continue without OCR.
4. If the text is missing or insufficient, process the document with Optical Character Recognition (OCR).

This approach avoids unnecessary OCR while still supporting scanned or image-based documents.

## Document Classification

Documents are assigned to one of two initial processing paths:

- machine-readable PDF;
- scanned or image-based document requiring OCR.

This classification takes place early in the ingestion pipeline because the two document types require different preprocessing steps.

## LLM Processing Architecture

TERA uses two separate LLM modules with distinct responsibilities.

### 1. Structured Extraction Module

The first module transforms extracted document text into structured JSON. It identifies relevant travel expense information and maps it to the current schema.

### 2. Human-Readable Review Module

The second module transforms structured data and validation findings into clear, reviewer-facing output. Its purpose is to help an employee or reviewer understand the extracted information, detected issues, and relevant findings.

## Separation of Responsibilities

The processing pipeline separates document handling, structured extraction, validation, and presentation:

- PDF extraction and OCR produce usable text;
- the Structured Extraction Module converts text into JSON;
- validation logic checks the structured data against defined rules;
- the Human-Readable Review Module presents the results to the reviewer.

This separation makes individual components easier to evaluate, test, and replace during the research phase.
