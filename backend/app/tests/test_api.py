from datetime import date

import pytest
from fastapi import HTTPException

from app import seed
from app.db import connect
from app.main import (
    LendIn, LendPreviewIn, SettingsIn, board, lend, lend_preview, loans,
    save_settings, settings,
)


@pytest.fixture()
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    yield


def test_seed_overdue_against_default_today(db):
    snap = board()
    # 种子样例应还 2020-06-01，默认业务日是真实今天，故逾期；但 items.status 不参与分类。
    assert snap["business_date"] == date.today().isoformat()
    assert snap["counts"]["overdue"] == 1
    assert snap["counts"]["available"] == 3  # 已外借样例仍是 on_loan，不会因逾期变 available


def test_move_business_date_to_2019_reclassifies_without_touching_status(db):
    snap = save_settings(SettingsIn(business_date="2019-01-01"))
    b, l = snap["board"], snap["loans"]
    # 改判规则一次贯穿顶细条/分栏/借还记录：2019 时种子样例不是逾期。
    assert b["business_date"] == "2019-01-01"
    assert b["counts"] == {"available": 3, "active": 1, "overdue": 0}
    assert len(b["active"]) == 1 and b["overdue"] == []
    assert len(l["active"]) == 1 and l["overdue"] == []
    # 同一笔借款在两个快照里判定必须一致，禁止顶条/在借栏各过一套。
    assert b["active"][0]["id"] == l["active"][0]["id"]
    # items.status 与在借行不因改日变成 available。
    c = connect()
    assert c.execute("SELECT status FROM items WHERE id=4").fetchone()["status"] == "on_loan"
    c.close()
    # 随后 GET 与保存快照同源。
    assert board()["counts"] == b["counts"]


def test_invalid_business_date_rolls_back_everything(db):
    before = settings().get("business_date")
    for bad in ("20190101", "2019-02-30", "nope", None):
        with pytest.raises(HTTPException) as ei:
            save_settings(SettingsIn(business_date=bad))
        assert ei.value.status_code == 400
    # 设置与顶细条都停在改之前。
    assert settings()["business_date"] == before
    assert board()["business_date"] == before


def test_preview_and_submit_share_one_rule_across_date_change(db):
    # 业务日 2019：应还 2018 的预演不通过（按当前业务日，不按旧日）。
    save_settings(SettingsIn(business_date="2019-01-01"))
    pv = lend_preview(1, LendPreviewIn(due_date="2018-06-01"))
    assert pv["ok"] is False and pv["reason"] == "due_before_business_date"
    with pytest.raises(HTTPException) as ei:
        lend(1, LendIn(borrower="甲", due_date="2018-06-01"))
    assert ei.value.status_code == 409  # 提交瞬间与预演同一规则
    # 预演按旧日挑了可借物，提交时业务日已变到 2017：资格重新成立，提交成功。
    save_settings(SettingsIn(business_date="2017-01-01"))
    pv2 = lend_preview(1, LendPreviewIn(due_date="2018-06-01"))
    assert pv2["ok"] is True and pv2["business_date"] == "2017-01-01"
    out = lend(1, LendIn(borrower="甲", due_date="2018-06-01"))
    assert out["loan_id"] > 0
    b = board()
    # 2017 业务日下该笔在借不逾期，物品已实际落库为 on_loan。
    assert b["counts"]["available"] == 2 and b["counts"]["active"] == 2 and b["counts"]["overdue"] == 0
    c = connect()
    assert c.execute("SELECT status FROM items WHERE id=1").fetchone()["status"] == "on_loan"
    c.close()


def test_overdue_reappears_when_date_moves_forward(db):
    save_settings(SettingsIn(business_date="2019-01-01"))
    assert board()["counts"]["overdue"] == 0
    snap = save_settings(SettingsIn(business_date="2020-06-02"))
    assert snap["board"]["counts"]["overdue"] == 1
    assert snap["loans"]["overdue"][0]["overdue"] is True
