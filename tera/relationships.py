"""Apply explicit reviewer decisions about documents representing the same expense."""

DUPLICATE_PREFIXES = (
    "Möglicher Doppelbeleg;",
    "Möglicherweise dieselbe Ausgabe",
    "Zusammengehörige Belege mit",
    "Gemeinsame Referenz, aber",
)


def apply_relationship_decisions(records):
    by_id = {r["document_id"]: r for r in records}
    events = {}
    for record in records:
        history = record.get("relationship_history", [])
        if history:
            event = history[-1]
            events[event["id"]] = event
    for event in events.values():
        members = [by_id[i] for i in event["document_ids"] if i in by_id]
        if (
            len(members) != len(event["document_ids"])
            or any(
                not r.get("relationship_history")
                or r["relationship_history"][-1]["id"] != event["id"]
                for r in members
            )
            or event["resolution"] == "pending"
        ):
            continue
        ids = set(event["document_ids"])
        for record in members:
            outside = set(record.get("related_document_ids", [])) - ids
            if not outside:
                record["warnings"] = [
                    w for w in record["warnings"] if not w.startswith(DUPLICATE_PREFIXES)
                ]
            record["related_document_ids"] = list(
                dict.fromkeys(
                    record.get("related_document_ids", [])
                    + [i for i in event["document_ids"] if i != record["document_id"]]
                )
            )
            record["duplicate_of"] = (
                event["primary_document_id"]
                if event["resolution"] == "same_expense"
                and record["document_id"] != event["primary_document_id"]
                else None
            )


def explicitly_separate(left, right):
    a, b = left.get("relationship_history", []), right.get("relationship_history", [])
    return bool(a and b and a[-1]["id"] == b[-1]["id"] and a[-1]["resolution"] == "separate")
