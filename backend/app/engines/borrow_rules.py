"""Business-date driven rules: one active loan per item, overdue detection,
and the single eligibility check shared by lend preview (frontend) and
lend submission (API)."""

from datetime import date


def parse_iso_date(value) -> date | None:
    """Strict YYYY-MM-DD. Rejects e.g. 20190101 / 2019-2-3 / 2019-02-30."""
    if not isinstance(value, str):
        return None
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return None
    return d if d.isoformat() == value else None


def can_lend(item_status: str, active_loans: int,
             due_date: str | None = None, business_date: str | None = None) -> dict:
    if item_status != "available":
        return {"ok": False, "reason": "item_not_available"}
    if active_loans > 0:
        return {"ok": False, "reason": "already_on_loan"}
    if due_date is not None:
        if parse_iso_date(due_date) is None:
            return {"ok": False, "reason": "invalid_due_date"}
        if business_date is not None and due_date < business_date:
            return {"ok": False, "reason": "due_before_business_date"}
    return {"ok": True, "reason": ""}


def is_overdue(due_date: str, business_date: str, loan_status: str) -> bool:
    if loan_status != "active":
        return False
    return bool(due_date) and due_date < business_date


def classify_loans(loans: list[dict], business_date: str) -> dict:
    active, overdue, returned = [], [], []
    for L in loans:
        st = L.get("status")
        if st == "returned":
            returned.append(L)
        elif is_overdue(L.get("due_date"), business_date, st):
            overdue.append({**L, "overdue": True})
        elif st == "active":
            active.append({**L, "overdue": False})
    return {"active": active, "overdue": overdue, "returned": returned}
