"""Apply a user's confirmed correction, retaining an immutable before/after audit."""

from copy import deepcopy

from tera.reconciliation import reconcile
from tera.schemas import ReceiptFacts


def corrected_record(record, facts: ReceiptFacts, user_id, user_name, timestamp, comment):
    facts = facts.model_copy(deep=True)
    facts.notes, facts.notices, facts.evidence = [], [], []
    for item in facts.items:
        item.evidence = []
    facts, issues, derived, reconciled = reconcile(facts)
    if issues:
        raise ValueError(" ".join(dict.fromkeys(issue.message for issue in issues)))
    result = deepcopy(record)
    updated = facts.model_dump(
        mode="json", exclude={"notes", "notices", "evidence", "multiple_receipts"}
    )
    result.setdefault("correction_history", []).append(
        {
            "before": deepcopy(record["facts"]),
            "after": deepcopy(updated),
            "previous_warnings": list(record["warnings"]),
            "user_id": user_id,
            "user_name": user_name,
            "corrected_at": timestamp,
            "comment": comment.strip(),
        }
    )
    result.update(
        facts=updated,
        warnings=[],
        validation_issues=[],
        derived_fields=derived,
        items_reconciled=reconciled,
        extraction_failed=False,
    )
    result.setdefault("review_history", []).append(
        {
            "decision": "approved",
            "comment": comment.strip(),
            "user_id": user_id,
            "user_name": user_name,
            "reviewed_at": timestamp,
        }
    )
    return result
