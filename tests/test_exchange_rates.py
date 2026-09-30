from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from tera import exchange_rates
from tera.reporting import make_report, merge_fragments
from tera.schemas import ReceiptFacts


def test_bank_adapter_validates_direction_date_and_caches(monkeypatch):
    calls = []

    def request(request):
        calls.append(request)
        assert dict(request.url.params)["amount"] == "1"
        return httpx.Response(
            200,
            json={
                "result": {
                    "success": True,
                    "historical": True,
                    "date": "2026-07-29",
                    "query": {"from": "CNY", "to": "EUR", "amount": 1},
                    "info": {"timestamp": 1785369599, "quote": 0.128878},
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(request))
    monkeypatch.setattr(exchange_rates.httpx, "Client", lambda **_: client)
    exchange_rates.historical_rate.cache_clear()
    result = exchange_rates.historical_rate("CNY", date(2026, 7, 29))
    assert result["rate"] == "0.128878"
    assert result["as_of"] == "2026-07-29"
    assert exchange_rates.historical_rate("CNY", date(2026, 7, 29)) == result
    assert len(calls) == 1
    exchange_rates.historical_rate.cache_clear()


@pytest.mark.parametrize(
    "mutation",
    [
        {"success": False},
        {"date": "2026-07-28"},
        {"query": {"from": "EUR", "to": "CNY", "amount": 1}},
        {"info": {"timestamp": 1785369599, "quote": -1}},
    ],
)
def test_bank_adapter_rejects_wrong_responses(monkeypatch, mutation):
    data = {
        "success": True,
        "historical": True,
        "date": "2026-07-29",
        "query": {"from": "CNY", "to": "EUR", "amount": 1},
        "info": {"timestamp": 1785369599, "quote": 0.128878},
        **mutation,
    }
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"result": data}))
    )
    monkeypatch.setattr(exchange_rates.httpx, "Client", lambda **_: client)
    exchange_rates.historical_rate.cache_clear()
    with pytest.raises(ValueError):
        exchange_rates.historical_rate("CNY", date(2026, 7, 29))


def test_missing_rate_never_becomes_zero_and_original_totals_survive(monkeypatch):
    def offline(*_):
        raise TimeoutError("unavailable")

    monkeypatch.setattr(exchange_rates, "historical_rate", offline)
    facts = ReceiptFacts(
        merchant="Hotel",
        invoice_date="2026-07-29",
        category="Hotel",
        currency="CNY",
        total="278.98",
        items=[{"description": "Zimmer", "category": "Hotel", "gross": "278.98"}],
    )
    record = merge_fragments(
        SimpleNamespace(id="test", filename="hotel.pdf", sha256="abc", page_count=1),
        [facts],
        [],
        [],
    )
    exchange_rates.attach_rate(record)
    report = make_report([record], "test", "test")
    assert report["expenses"][0]["amount_eur"] is None
    assert report["totals"]["eur"][0]["unknown_amounts"] == 1
    assert report["totals"]["by_currency"][0]["confirmed"] == "278.98"
    assert report["expenses"][0]["exchange_rate"]["error"]
    record["exchange_rate"] = {
        "currency": "CNY",
        "rate": "0.128878",
        "requested_on": "2026-07-29",
        "as_of": "2026-07-29",
    }
    exchange_rates.attach_rate(record)  # Reuses saved rate, even while provider is offline.
    report = make_report([record], "test", "test")
    assert report["totals"]["eur"][0]["confirmed"] == "35.95"
    record["review_history"] = [{"decision": "rejected"}]
    report = make_report([record], "test", "test")
    assert report["totals"]["eur"][0]["excluded"] == "35.95"
    record["facts"]["invoice_date"] = "2026-07-28"
    exchange_rates.attach_rate(record)
    assert record["exchange_rate"]["rate"] is None
