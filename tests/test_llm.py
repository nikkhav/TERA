import json

import pytest

from tera.config import Settings
from tera.llm import OllamaExtractor


def run_extractor(monkeypatch, result, think=None):
    from tera import llm

    class Client:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, url, json):
            assert url.endswith("/api/generate")
            assert json["format"] == "json"
            assert json["options"]["num_predict"] > 0
            assert json["model"] == "test-model"
            if think is None:
                assert "think" not in json
            else:
                assert json["think"] is think
            self.payload = json
            return self

        def raise_for_status(self):
            pass

        def json(self):
            return result

    monkeypatch.setattr(llm.httpx, "Client", Client)
    return OllamaExtractor(
        Settings(_env_file=None, ollama_model="test-model", ollama_think=think)
    ).extract("receipt", [{"page": 2, "text": "Hotel\nTotal EUR 712.60", "part": 1}])


def test_valid_model_response(monkeypatch):
    facts = run_extractor(
        monkeypatch,
        {
            "done": True,
            "done_reason": "stop",
            "response": json.dumps(
                {
                    "total": "712.60",
                    "currency": "EUR",
                    "evidence": [{"page": 2, "quote": "Total EUR 712.60"}],
                }
            ),
        },
    )
    assert str(facts.total) == "712.60"


@pytest.mark.parametrize("page,quote", [(1, "Hotel"), (2, "invented")])
def test_model_cannot_cite_unseen_text(monkeypatch, page, quote):
    facts = run_extractor(
        monkeypatch,
        {"done": True, "response": json.dumps({"evidence": [{"page": page, "quote": quote}]})},
    )
    assert not facts.evidence
    assert any("nicht im Dokument gefunden" in note for note in facts.notes)


def test_truncated_model_output_is_rejected(monkeypatch):
    with pytest.raises(ValueError, match="truncated"):
        run_extractor(monkeypatch, {"done": True, "done_reason": "length", "response": "{}"})


def test_missing_evidence_requires_review(monkeypatch):
    assert run_extractor(monkeypatch, {"done": True, "response": "{}"}).notes


@pytest.mark.parametrize("think", [True, False])
def test_thinking_is_configured_without_model_name_rules(monkeypatch, think):
    run_extractor(monkeypatch, {"done": True, "response": "{}"}, think=think)
