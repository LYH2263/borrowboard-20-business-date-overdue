from app.engines.borrow_rules import can_lend, is_overdue, classify_loans, parse_iso_date


def test_mutex():
    assert can_lend("available", 0)["ok"]
    assert can_lend("available", 1)["reason"] == "already_on_loan"
    assert can_lend("retired", 0)["ok"] is False


def test_overdue():
    assert is_overdue("2020-01-01", "2026-01-01", "active")
    assert not is_overdue("2020-01-01", "2026-01-01", "returned")


def test_overdue_follows_business_date():
    # 同一笔在借：业务日推到 2019 时不改判为逾期；回到 2020 应还日后即逾期。
    loan = {"id": 1, "status": "active", "due_date": "2020-06-01"}
    assert classify_loans([loan], "2019-01-01")["overdue"] == []
    r = classify_loans([loan], "2020-06-02")
    assert len(r["overdue"]) == 1 and r["active"] == []
    # 应还日当天不算逾期。
    assert classify_loans([loan], "2020-06-01")["overdue"] == []


def test_classify():
    r = classify_loans([
        {"id": 1, "status": "active", "due_date": "2020-01-01"},
        {"id": 2, "status": "active", "due_date": "2099-01-01"},
        {"id": 3, "status": "returned", "due_date": "2020-01-01"},
    ], "2026-01-01")
    assert len(r["overdue"]) == 1 and len(r["active"]) == 1 and len(r["returned"]) == 1


def test_parse_iso_date_strict():
    assert parse_iso_date("2019-02-03") is not None
    for bad in ("20190101", "2019-2-3", "2019-02-30", "not-a-date", "", None):
        assert parse_iso_date(bad) is None


def test_can_lend_respects_business_date():
    assert can_lend("available", 0, due_date="2019-01-01", business_date="2018-12-31")["ok"]
    r = can_lend("available", 0, due_date="2019-01-01", business_date="2019-02-01")
    assert r["reason"] == "due_before_business_date"
    assert can_lend("available", 0, due_date="2019-02-30", business_date="2019-01-01")["reason"] == "invalid_due_date"
    # 不传业务日时保持纯物品资格语义。
    assert can_lend("available", 0, due_date="2000-01-01")["ok"]
