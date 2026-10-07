import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with TestClient(app) as c:
        yield c


def _set_date(client, day):
    return client.put("/api/settings", json={"values": {"business_date": day}})


def test_seed_sample_reclassified_at_2019(client):
    # Seed loan: item 4 on_loan, due 2020-06-01. Under a 2026 day it is overdue.
    r = _set_date(client, "2026-10-06")
    assert r.status_code == 200
    board = r.json()["board"]
    assert board["business_date"] == "2026-10-06"
    assert board["counts"]["overdue"] == 1
    assert [l["id"] for l in board["overdue"]] == [1]

    # Move the business date back to 2019: the same loan is active again.
    r = _set_date(client, "2019-01-01")
    assert r.status_code == 200
    saved = r.json()
    board = saved["board"]
    loans = saved["loans"]
    assert board["business_date"] == "2019-01-01"
    assert board["counts"] == {"available": 3, "active": 1, "overdue": 0}
    assert board["overdue"] == [] and len(board["active"]) == 1
    # The save response's loan history uses the same saved date.
    assert loans["business_date"] == "2019-01-01"
    assert loans["overdue"] == [] and len(loans["active"]) == 1

    # items.status must not be rewritten by a date change.
    items = {i["id"]: i for i in client.get("/api/items").json()}
    assert items[4]["status"] == "on_loan"
    titles = [i["title"] for i in board["available"]]
    assert "已外借样例" not in titles

    # And a fresh GET agrees with the save response.
    fresh = client.get("/api/board").json()
    assert fresh["counts"] == board["counts"]
    assert [l["id"] for l in fresh["active"]] == [l["id"] for l in board["active"]]


def test_invalid_business_date_rolls_back(client):
    ok = _set_date(client, "2026-10-06")
    assert ok.status_code == 200
    before = client.get("/api/board").json()

    for bad in ["2019-02-30", "2019/01/01", "2019-1-1", "not-a-date"]:
        r = _set_date(client, bad)
        assert r.status_code == 400, bad

    # Setting and every overdue verdict are back to / stay at the pre-edit state.
    assert client.get("/api/settings").json()["business_date"] == "2026-10-06"
    after = client.get("/api/board").json()
    assert after["business_date"] == "2026-10-06"
    assert after["counts"] == before["counts"]
    assert [l["id"] for l in after["overdue"]] == [l["id"] for l in before["overdue"]]


def test_stale_preview_checked_against_submit_time_state(client):
    _set_date(client, "2019-01-01")
    iid = client.post("/api/items", json={"title": "梯子", "owner": "老周"}).json()["id"]

    # Preview under the old day: item is borrowable.
    preview = client.get("/api/board").json()
    assert iid in [i["id"] for i in preview["available"]]

    # The day moves before confirmation; submit-time eligibility still passes
    # because stored state is re-checked, and the returned board is already
    # classified under the new day (a past due date makes it overdue).
    _set_date(client, "2021-01-01")
    r = client.post(f"/api/items/{iid}/lend", json={"borrower": "邻居乙", "due_date": "2019-06-01"})
    assert r.status_code == 200, r.text
    board = r.json()["board"]
    assert board["business_date"] == "2021-01-01"
    assert iid not in [i["id"] for i in board["available"]]
    new_loan = next(l for l in board["overdue"] if l["item_id"] == iid)
    assert new_loan["overdue"] is True
    assert board["counts"]["overdue"] == len(board["overdue"])

    # A second confirmation from the stale preview cannot pass: one active loan.
    r = client.post(f"/api/items/{iid}/lend", json={"borrower": "重复", "due_date": "2019-07-01"})
    assert r.status_code == 409

    # Bad due date is rejected at submit regardless of preview contents.
    r = client.post("/api/items/1/lend", json={"borrower": "x", "due_date": "2019/01/01"})
    assert r.status_code == 400


def test_strip_and_panes_never_disagree(client):
    # 2019: nothing overdue anywhere, and no active row carries the overdue mark.
    _set_date(client, "2019-01-01")
    board = client.get("/api/board").json()
    assert board["counts"]["overdue"] == 0
    assert all(not l.get("overdue") for l in board["active"])
    assert all(not l.get("overdue") for l in board["overdue"])

    loans = client.get("/api/loans").json()
    assert loans["business_date"] == "2019-01-01"
    assert loans["overdue"] == []

    # 2021: the same row is overdue in the strip, the pane and the history.
    _set_date(client, "2021-01-01")
    board = client.get("/api/board").json()
    loans = client.get("/api/loans").json()
    assert board["counts"]["overdue"] == 1
    assert board["overdue"][0]["overdue"] is True
    assert loans["overdue"][0]["id"] == board["overdue"][0]["id"]
    # No row is both in the on-loan section and marked overdue.
    on_loan_ids = {l["id"] for l in board["active"]}
    assert all(l["id"] not in on_loan_ids for l in board["overdue"])
    assert all(not l.get("overdue") for l in board["active"])


def test_return_makes_item_available_not_date_change(client):
    _set_date(client, "2019-01-01")  # seed loan not overdue here
    lid = client.get("/api/loans").json()["active"][0]["id"]
    assert client.post(f"/api/loans/{lid}/return").status_code == 200
    board = client.get("/api/board").json()
    item4 = next(i for i in client.get("/api/items").json() if i["id"] == 4)
    assert item4["status"] == "available"
    assert 4 in [i["id"] for i in board["available"]]
    assert board["counts"]["active"] == 0
