"""Business date, one-active-loan-per-item and overdue classification.

Overdue is always computed against the *business date* (a saved setting),
never the machine clock. Item/loan rows keep their persisted status; only the
display classification changes with the date.
"""
from datetime import date, datetime

BUSINESS_DATE_KEY = "business_date"


def parse_business_date(value):
    """Strictly parse a business-date value; raise ValueError when invalid."""
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("bad_business_date")
    # datetime.strptime is lenient about nothing here, but the explicit
    # length check rejects e.g. "2019-1-1" and trailing whitespace.
    datetime.strptime(value, "%Y-%m-%d")
    return value


def effective_business_date(value, fallback):
    """Return the stored business date, or fallback when unset/garbage."""
    try:
        return parse_business_date(value)
    except (TypeError, ValueError):
        return fallback


def can_lend(item_status: str, active_loans: int) -> dict:
    if item_status != "available":
        return {"ok": False, "reason": "item_not_available"}
    if active_loans > 0:
        return {"ok": False, "reason": "already_on_loan"}
    return {"ok": True, "reason": ""}

def is_overdue(due_date, business_date, loan_status: str) -> bool:
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
            # Changing the business date must never turn an on-loan item
            # into an available one: active loans stay in the on-loan pane.
            active.append({**L, "overdue": False})
    return {"active": active, "overdue": overdue, "returned": returned}
