from copy import deepcopy
from types import SimpleNamespace

from tera import localization
from tera.config import Settings
from tera.reporting import merge_fragments
from tera.schemas import ReceiptFacts


def record():
    facts = ReceiptFacts(
        merchant="旅馆",
        total="278.98",
        items=[{"description": "房费", "gross": "278.98"}],
        evidence=[{"page": 1, "field": "total", "quote": "总金额 278.98"}],
        notices=["This invoice is fictional."],
    )
    return merge_fragments(
        SimpleNamespace(id="test", filename="test.pdf", sha256="abc", page_count=1), [facts], [], []
    )


def test_translation_never_changes_amounts_or_source_quotes(monkeypatch):
    value = record()
    before = deepcopy(value)
    monkeypatch.setattr(
        localization, "translate_texts", lambda texts, *_: ["Deutsche Bezeichnung"] * len(texts)
    )
    localization.localize_record(value, Settings())
    assert value["facts"]["total"] == before["facts"]["total"]
    assert value["sources"] == before["sources"]
    assert value["facts"]["items"][0]["gross"] == "278.98"
    assert value["facts"]["items"][0]["description"] == "Deutsche Bezeichnung"
    assert value["original_texts"]["items"] == ["房费"]
    assert value["notices"] == ["Deutsche Bezeichnung"]


def test_translation_failure_is_visible_and_original_is_retained(monkeypatch):
    def fail(*_):
        raise TimeoutError("offline")

    monkeypatch.setattr(localization, "translate_texts", fail)
    value = record()
    localization.localize_record(value, Settings())
    assert "Übersetzung nicht vollständig" in value["warnings"][-1]
    assert not localization.FOREIGN_SCRIPT.search(value["facts"]["items"][0]["description"])
    assert value["original_texts"]["items"] == ["房费"]


def test_notice_filter_accepts_empty_boilerplate_but_keeps_warning(monkeypatch):
    import httpx

    from tera.localization import translate_texts

    response = {"done": True, "response": '{"texts":["Dieser Beleg ist fiktiv.", ""]}'}
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
    )
    monkeypatch.setattr(localization.httpx, "Client", lambda **_: client)
    values = translate_texts(
        ["This invoice is fictional.", "Thank you for booking."], Settings(), [0, 1]
    )
    assert values == ["Dieser Beleg ist fiktiv.", ""]
