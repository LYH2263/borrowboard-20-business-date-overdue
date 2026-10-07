from app.engines.borrow_rules import (
    can_lend, is_overdue, classify_loans,
    parse_business_date, effective_business_date,
)
import pytest

def test_mutex():
    assert can_lend("available", 0)["ok"]
    assert can_lend("available", 1)["reason"] == "already_on_loan"
    assert can_lend("retired", 0)["ok"] is False

def test_overdue():
    assert is_overdue("2020-01-01", "2026-01-01", "active")
    assert not is_overdue("2020-01-01", "2026-01-01", "returned")
    # Due exactly on the business date is not overdue yet.
    assert not is_overdue("2026-01-01", "2026-01-01", "active")

def test_classify():
    r = classify_loans([
        {"id": 1, "status": "active", "due_date": "2020-01-01"},
        {"id": 2, "status": "active", "due_date": "2099-01-01"},
        {"id": 3, "status": "returned", "due_date": "2020-01-01"},
    ], "2026-01-01")
    assert len(r["overdue"]) == 1 and len(r["active"]) == 1 and len(r["returned"]) == 1
    assert r["overdue"][0]["overdue"] is True and r["active"][0]["overdue"] is False

def test_classify_is_date_only():
    """Moving the business date reclassifies overdue<->active but never
    removes an active loan from the on-loan side."""
    loan = {"id": 1, "status": "active", "due_date": "2020-06-01"}
    before = classify_loans([loan], "2019-01-01")
    after = classify_loans([loan], "2021-01-01")
    assert len(before["active"]) == 1 and before["overdue"] == []
    assert len(after["overdue"]) == 1 and after["active"] == []
    assert "available" not in before and "available" not in after

@pytest.mark.parametrize("bad", ["2019/01/01", "2019-1-1", "2019-02-30", "2019-13-01", "", "x", None])
def test_parse_business_date_rejects(bad):
    with pytest.raises((ValueError, TypeError)):
        parse_business_date(bad)

@pytest.mark.parametrize("good", ["2019-01-01", "2026-12-31"])
def test_parse_business_date_accepts(good):
    assert parse_business_date(good) == good

def test_effective_falls_back():
    assert effective_business_date(None, "2026-01-01") == "2026-01-01"
    assert effective_business_date("garbage", "2026-01-01") == "2026-01-01"
    assert effective_business_date("2019-01-01", "2026-01-01") == "2019-01-01"
