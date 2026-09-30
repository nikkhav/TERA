"""Bankenverband calculator adapter; snapshots make saved reports reproducible."""

import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import lru_cache

import httpx

from tera.currency_exchange import ExchangeRate, convert_amount

logger = logging.getLogger(__name__)
SOURCE_URL = "https://bankenverband.de/services/waehrungsrechner"
ENDPOINT = "https://bankenverband.de/api/converter/convert"


@lru_cache(maxsize=1024)
def historical_rate(currency: str, requested_on: date) -> dict:
    if requested_on >= datetime.now(UTC).date():
        raise ValueError("A completed historical rate date is required")
    with httpx.Client(timeout=10) as client:
        response = client.get(
            ENDPOINT,
            params={
                "from": currency,
                "to": "EUR",
                "amount": "1",
                "date": requested_on.isoformat(),
                "decimals": "5",
                "interbank": "0",
                "key": requested_on.isoformat(),
            },
        )
        response.raise_for_status()
        data = response.json()["result"]
    if (
        not data
        or data.get("success") is not True
        or data.get("historical") is not True
        or data.get("date") != requested_on.isoformat()
        or data.get("query") != {"from": currency, "to": "EUR", "amount": 1}
    ):
        raise ValueError("Unexpected calculator response")
    rate = Decimal(str(data["info"]["quote"]))
    as_of = datetime.fromtimestamp(data["info"]["timestamp"], UTC).date()
    if as_of > requested_on:
        raise ValueError("Calculator returned a later rate")
    checked = ExchangeRate(currency, "EUR", rate, as_of, "Bankenverband / CurrencyLayer")
    return {
        "currency": currency,
        "rate": str(checked.rate),
        "requested_on": requested_on.isoformat(),
        "as_of": as_of.isoformat(),
        "source": checked.source,
        "source_url": SOURCE_URL,
        "error": None,
    }


def attach_rate(record):
    facts = record["facts"]
    currency, day = facts.get("currency"), facts.get("invoice_date")
    if currency == "EUR":
        record["exchange_rate"] = None
        return
    previous = record.get("exchange_rate")
    if (
        previous
        and previous.get("rate")
        and previous.get("currency") == currency
        and previous.get("requested_on") == day
    ):
        return
    try:
        record["exchange_rate"] = dict(historical_rate(currency, date.fromisoformat(day)))
    except Exception:
        logger.exception("exchange_rate_unavailable currency=%s date=%s", currency, day)
        record["exchange_rate"] = {
            "currency": currency,
            "requested_on": day,
            "rate": None,
            "as_of": None,
            "source": "Bankenverband / CurrencyLayer",
            "source_url": SOURCE_URL,
            "error": "EUR-Umrechnung nicht verfügbar. Kursdatum und Währung prüfen.",
        }


def euro_amount(amount, currency, snapshot):
    if amount is None:
        return None
    if currency == "EUR":
        return str(
            convert_amount(amount, ExchangeRate("EUR", "EUR", "1", datetime.now(UTC).date()))
        )
    if not snapshot or not snapshot.get("rate") or snapshot.get("currency") != currency:
        return None
    rate = ExchangeRate(currency, "EUR", snapshot["rate"], date.fromisoformat(snapshot["as_of"]))
    return str(convert_amount(amount, rate))
