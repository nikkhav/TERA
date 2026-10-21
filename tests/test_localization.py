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
        localization,
        "translate_texts",
        lambda texts, *_: [
            "Deutsche Bezeichnung 278.98" if "278.98" in text else "Deutsche Bezeichnung"
            for text in texts
        ],
    )
    localization.localize_record(value, Settings())
    assert value["facts"]["total"] == before["facts"]["total"]
    assert [s["quote"] for s in value["sources"]] == [s["quote"] for s in before["sources"]]
    assert value["sources"][0]["translation"] == "Deutsche Bezeichnung 278.98"
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
    assert value["facts"]["items"][0]["description"] == "房费"
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


def test_readable_merchant_and_german_warnings_do_not_need_translation(monkeypatch):
    value = record()
    value["facts"]["merchant"] = "Rasier Pacific Pty Ltd"
    value["facts"]["items"][0]["description"] = "Fahrtkosten"
    value["warnings"] = ["Gesamtbetrag im Original prüfen."]
    value["notices"] = []
    value["sources"] = []

    def unexpected(*_):
        raise AssertionError("Readable German text and original Latin names must be retained")

    monkeypatch.setattr(localization, "translate_texts", unexpected)
    localization.localize_record(value, Settings(_env_file=None))
    assert value["facts"]["merchant"] == "Rasier Pacific Pty Ltd"
    assert value["warnings"] == ["Gesamtbetrag im Original prüfen."]


def test_bad_source_translation_cannot_change_the_original_amount(monkeypatch):
    value = record()
    monkeypatch.setattr(
        localization, "translate_texts", lambda texts, *_: ["Betrag 999.99"] * len(texts)
    )
    localization.localize_record(value, Settings(_env_file=None))
    assert value["sources"][0]["quote"] == "总金额 278.98"
    assert value["sources"][0]["translation"] is None
    assert "Übersetzung nicht vollständig" in value["warnings"][-1]


def test_batch_translation_failure_retries_individual_texts(monkeypatch):
    value = record()
    calls = []

    def translate(texts, *_):
        calls.append(len(texts))
        if len(texts) > 1:
            raise ValueError("one bad batch")
        return ["Betrag 278.98" if "278.98" in texts[0] else "Deutsche Bezeichnung"]

    monkeypatch.setattr(localization, "translate_texts", translate)
    localization.localize_record(value, Settings(_env_file=None))
    assert calls[0] > 1
    assert value["sources"][0]["translation"] == "Betrag 278.98"
    assert value["facts"]["items"][0]["description"] == "Deutsche Bezeichnung"
    assert not any("Übersetzung nicht vollständig" in text for text in value["warnings"])


def test_source_numbers_are_restored_from_protected_placeholders(monkeypatch):
    import httpx

    captured = []

    def respond(request):
        import json

        captured.append(json.loads(request.content)["prompt"])
        return httpx.Response(
            200, json={"done": True, "response": '{"texts":["Gesamtbetrag __TERA_NUM_0__"]}'}
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(localization.httpx, "Client", lambda **_: client)
    assert localization.translate_texts(["总金额 278.98"], Settings(_env_file=None)) == [
        "Gesamtbetrag 278.98"
    ]
    assert "278.98" not in captured[0]


def test_chinese_dates_and_am_pm_translate_without_model(monkeypatch):
    value = record()
    value["facts"]["merchant"] = "Uber"
    value["facts"]["items"] = []
    value["notices"] = []
    value["sources"] = [
        {"quote": "2026 年 5 月 12 日"},
        {"quote": "下午3:00"},
    ]
    monkeypatch.setattr(
        localization, "translate_texts", lambda *_: (_ for _ in ()).throw(AssertionError())
    )
    localization.localize_record(value, Settings())
    assert value["sources"][0]["translation"] == "Datum: 2026-5-12"
    assert value["sources"][1]["translation"] == "Nachmittags 3:00"
    assert not any("Übersetzung" in warning for warning in value["warnings"])
