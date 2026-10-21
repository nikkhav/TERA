"""Keep flight itineraries distinct from accommodation details."""

from datetime import date

from tera.reconciliation import reconcile
from tera.schemas import ReceiptFacts
from tera.transport import attach_flight_route, route_label


def test_round_trip_uses_printed_stops_and_precise_source():
    text = "CZ332/CZ643/CZ322/CZ331  FRA-CAN-MEL-CAN-FRA(Q/Q/A/A舱)"
    facts = ReceiptFacts(category="Flugreisen", origin="FRA", destination="FRA")
    pages = [{"page": 1, "text": text, "blocks": [{"id": "p1-r17", "start": 0, "end": len(text)}]}]
    attach_flight_route(facts, pages)
    assert facts.flight_route == "FRA → CAN → MEL → CAN → FRA"
    assert route_label(facts.model_dump()) == facts.flight_route
    source = facts.evidence[0]
    assert source.block_id == "p1-r17"
    assert text[source.start : source.end] == source.quote == "FRA-CAN-MEL-CAN-FRA"


def test_route_is_not_guessed_from_flight_numbers_or_conflicting_chains():
    facts = ReceiptFacts(
        category="Flugreisen", origin="FRA", destination="FRA", flight_route="FRA → MEL → FRA"
    )
    attach_flight_route(facts, [{"page": 1, "text": "CZ332/CZ643/CZ322/CZ331"}])
    assert facts.flight_route is None
    assert route_label(facts.model_dump()) == "Hin- und Rückflug (FRA)"
    attach_flight_route(facts, [{"page": 1, "text": "FRA-CAN-MEL\nMEL-CAN-FRA"}])
    assert facts.flight_route is None


def test_flight_segment_count_never_becomes_overnights():
    facts = ReceiptFacts(
        category="Flugreisen", currency="CNY", total="11600", overnight_count=4, room_count=1
    )
    checked, _, _, _ = reconcile(facts)
    assert checked.overnight_count is None
    assert checked.room_count is None
    assert checked.total == facts.total
    hotel = facts.model_copy(
        update={
            "category": "Hotel",
            "service_start": date(2026, 5, 2),
            "service_end": date(2026, 5, 6),
        }
    )
    checked, issues, _, _ = reconcile(hotel)
    assert checked.overnight_count == 4
    assert checked.room_count == 1
    assert not any(i.code == "overnight_mismatch" for i in issues)
