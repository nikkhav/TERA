from tera.prompts import RECHECK_RESERVE, build_prompt


def prompt_budget(settings) -> int:
    # A deliberately conservative UTF-8 byte budget, not a model tokenizer count.
    # Reserve both output tokens and room for Ollama's chat/template overhead.
    return settings.model_context_tokens - settings.model_output_tokens - 512


def chunk_pages(document_id: str, pages: list[dict], settings) -> list[list[dict]]:
    limit = prompt_budget(settings) - RECHECK_RESERVE
    chunks, current = [], []

    def part_page(page, part, start, text):
        result = {"page": page["page"], "part": part, "text": text, "text_start": start}
        if "blocks" in page:
            result["blocks"] = [
                block
                for block in page["blocks"]
                if block["start"] < start + len(text) and block["end"] > start
            ]
        return result

    for page in pages:
        remaining = page["text"]
        part = 1
        start = 0
        while remaining:
            whole = part_page(page, part, start, remaining)
            if len(build_prompt(document_id, current + [whole]).encode()) <= limit:
                current.append(whole)
                break
            if current:
                chunks.append(current)
                current = []
                continue
            low, high = 0, len(remaining)
            while low < high:
                middle = (low + high + 1) // 2
                candidate = part_page(page, part, start, remaining[:middle])
                if len(build_prompt(document_id, [candidate]).encode()) <= limit:
                    low = middle
                else:
                    high = middle - 1
            if low == 0:
                raise ValueError("Context budget is too small for the extraction prompt")
            # Prefer complete lines; otherwise retain every character across parts.
            cut = remaining.rfind("\n", 0, low)
            if cut >= 0:
                low = cut + 1
            chunks.append([part_page(page, part, start, remaining[:low])])
            remaining = remaining[low:]
            start += low
            part += 1
    if current:
        chunks.append(current)
    return chunks
