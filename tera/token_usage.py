"""Collect Ollama token counts for the active summary job."""

from contextvars import ContextVar

token_counts: ContextVar[list[int | None] | None] = ContextVar("token_counts", default=None)


def record_token_usage(response: dict) -> None:
    counts = token_counts.get()
    if counts is None:
        return

    prompt = response.get("prompt_eval_count")
    output = response.get("eval_count")
    counts.append(prompt + output if isinstance(prompt, int) and isinstance(output, int) else None)
