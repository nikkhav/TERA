"""Recover explicitly printed airport chains without inventing flight connections."""

import re

from tera.schemas import Category, Evidence

AIRPORT_CHAIN = re.compile(r"(?<![A-Z])([A-Z]{3}(?:\s*[-–—→/]\s*[A-Z]{3}){1,15})(?![A-Z])")


def attach_flight_route(facts, pages):
    if facts.category != Category.FLIGHTS:
        facts.flight_route = None
        return
    candidates = {}
    for page in pages:
        for match in AIRPORT_CHAIN.finditer(page["text"]):
            route = " → ".join(re.findall(r"[A-Z]{3}", match.group()))
            offset = page.get("text_start", 0)
            start, end = match.start() + offset, match.end() + offset
            block = next(
                (b for b in page.get("blocks", []) if b["start"] <= start and end <= b["end"]),
                None,
            )
            candidates.setdefault(
                route,
                Evidence(
                    field="flight_route",
                    page=page["page"],
                    quote=match.group(),
                    start=start,
                    end=end,
                    block_id=block["id"] if block else None,
                ),
            )
    requested = " → ".join(re.findall(r"[A-Z]{3}", facts.flight_route or ""))
    selected = (
        requested
        if requested in candidates
        else next(iter(candidates))
        if len(candidates) == 1
        else None
    )
    facts.flight_route = selected
    facts.evidence = [e for e in facts.evidence if e.field != "flight_route"]
    if selected:
        facts.evidence.append(candidates[selected])


def route_label(facts):
    if facts.get("flight_route") and facts.get("category") == "Flugreisen":
        return facts["flight_route"]
    origin, destination = facts.get("origin"), facts.get("destination")
    if not origin or not destination:
        return None
    if facts.get("category") == "Flugreisen" and origin.casefold() == destination.casefold():
        return f"Start und Ziel: {origin}"
    return f"{origin} → {destination}"
