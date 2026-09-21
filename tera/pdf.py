import pymupdf


def extract_pages(data: bytes, settings) -> list[dict]:
    if not data.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF file")
    try:
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass:
                raise ValueError("Password-protected PDF files are not supported")
            if not 1 <= len(pdf) <= settings.max_pdf_pages:
                raise ValueError(f"PDF must contain between 1 and {settings.max_pdf_pages} pages")
            pages = []
            characters = 0
            for page in pdf:
                content = page.get_text()
                if not content.strip():
                    raise ValueError(f"Page {page.number + 1} has no extractable text")
                characters += len(content)
                if characters > settings.max_text_characters:
                    raise ValueError("PDF exceeds the extracted text limit")
                pages.append({"page": page.number + 1, "text": content})
            return pages
    except (pymupdf.FileDataError, pymupdf.EmptyFileError) as exc:
        raise ValueError("Invalid or damaged PDF file") from exc
