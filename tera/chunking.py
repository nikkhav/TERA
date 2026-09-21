from tera.prompts import build_prompt


def prompt_budget(settings) -> int:
    # A deliberately conservative UTF-8 byte budget, not a model tokenizer count.
    # Reserve both output tokens and room for Ollama's chat/template overhead.
    return settings.model_context_tokens - settings.model_output_tokens - 512


def chunk_pages(document_id: str, pages: list[dict], settings) -> list[list[dict]]:
    limit = prompt_budget(settings)
    chunks, current = [], []
    for page in pages:
        remaining = page["text"]
        part = 1
        while remaining:
            whole = {"page": page["page"], "part": part, "text": remaining}
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
                candidate = {**whole, "text": remaining[:middle]}
                if len(build_prompt(document_id, [candidate]).encode()) <= limit:
                    low = middle
                else:
                    high = middle - 1
            if low == 0:
                raise ValueError("Context budget is too small for the extraction prompt")
            # Prefer complete lines; otherwise retain every character across parts.
            cut = remaining.rfind("\n", 0, low)
            if cut >= low // 2:
                low = cut + 1
            chunks.append([{**whole, "text": remaining[:low]}])
            remaining = remaining[low:]
            part += 1
    if current:
        chunks.append(current)
    return chunks
