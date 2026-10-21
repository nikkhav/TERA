import pymupdf


def extract_layout(page):
    """Group words on a visual row; retain coordinates and page-text offsets."""
    rows = []
    for word in sorted(page.get_text("words"), key=lambda w: (w[1], w[0])):
        # Different fonts on one baseline can have different top coordinates.
        center = (word[1] + word[3]) / 2
        match = next(
            (
                row
                for row in reversed(rows)
                if abs(center - (row[0][1] + row[0][3]) / 2)
                <= max(2, min(word[3] - word[1], row[0][3] - row[0][1]) * 0.25)
            ),
            None,
        )
        if match is not None:
            match.append(word)
        else:
            rows.append([word])
    text, blocks = "", []
    for index, row in enumerate(rows):
        row.sort(key=lambda w: w[0])
        line = "  ".join(w[4] for w in row) + "\n"
        blocks.append(
            {
                "id": f"p{page.number + 1}-r{index + 1}",
                "start": len(text),
                "end": len(text) + len(line),
                "bbox": [
                    round(v, 2)
                    for v in (
                        min(w[0] for w in row),
                        min(w[1] for w in row),
                        max(w[2] for w in row),
                        max(w[3] for w in row),
                    )
                ],
            }
        )
        text += line
    return text, blocks


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
                content, blocks = extract_layout(page)
                if not content.strip():
                    raise ValueError(f"Page {page.number + 1} has no extractable text")
                characters += len(content)
                if characters > settings.max_text_characters:
                    raise ValueError("PDF exceeds the extracted text limit")
                pages.append(
                    {
                        "page": page.number + 1,
                        "text": content,
                        "blocks": blocks,
                        "layout_version": 2,
                    }
                )
            return pages
    except (pymupdf.FileDataError, pymupdf.EmptyFileError) as exc:
        raise ValueError("Invalid or damaged PDF file") from exc
