from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.db import connect
from app.engines.borrow_rules import can_lend, classify_loans, parse_iso_date

app = FastAPI(title="Borrowboard", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BUSINESS_DATE_KEY = "business_date"


@app.on_event("startup")
def _startup(): seed.init_db()


@app.get("/api/health")
def health(): return {"ok": True, "project": "borrowboard"}


def _settings(c) -> dict:
    return {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}


def _business_date(c) -> str:
    row = c.execute("SELECT value FROM settings WHERE key=?", (BUSINESS_DATE_KEY,)).fetchone()
    return row["value"] if row else seed.DEFAULT_BUSINESS_DATE


def _board_snapshot(c, business_date: str) -> dict:
    # 可借栏只认真实落库的 items.status；改业务日不会重写它。
    available = [dict(r) for r in c.execute("SELECT * FROM items WHERE status='available'")]
    loans = [dict(r) for r in c.execute(
        """SELECT loans.*, items.title FROM loans JOIN items ON items.id=loans.item_id
           WHERE loans.status='active'""")]
    # 顶细条、在借栏、逾期段同源于这一次分类，不可能各算一套。
    cls = classify_loans(loans, business_date)
    return {
        "business_date": business_date,
        "available": available,
        "active": cls["active"],
        "overdue": cls["overdue"],
        "counts": {"available": len(available), "active": len(cls["active"]), "overdue": len(cls["overdue"])},
    }


def _loans_snapshot(c, business_date: str) -> dict:
    rows = [dict(r) for r in c.execute(
        "SELECT loans.*, items.title FROM loans JOIN items ON items.id=loans.item_id ORDER BY loans.id DESC")]
    cls = classify_loans(rows, business_date)
    return {"business_date": business_date, **cls}


@app.get("/api/items")
def items():
    c = connect(); rows = [dict(r) for r in c.execute("SELECT * FROM items")]; c.close(); return rows


@app.get("/api/board")
def board():
    c = connect()
    snap = _board_snapshot(c, _business_date(c))
    c.close()
    return snap


class ItemIn(BaseModel):
    title: str
    owner: str


@app.post("/api/items")
def add_item(body: ItemIn):
    c = connect()
    cur = c.execute("INSERT INTO items(title,owner,status,data_quality) VALUES (?,?,?,?)",
                    (body.title, body.owner, "available", "clean"))
    c.commit(); iid = cur.lastrowid; c.close(); return {"id": iid}


class LendIn(BaseModel):
    borrower: str
    due_date: str


@app.post("/api/items/{iid}/lend")
def lend(iid: int, body: LendIn):
    c = connect()
    business_date = _business_date(c)
    item = c.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
    if not item: c.close(); raise HTTPException(404, "item")
    active = c.execute("SELECT COUNT(*) c FROM loans WHERE item_id=? AND status='active'", (iid,)).fetchone()["c"]
    # 提交瞬间按当前业务日重判，与预演走同一函数、同一规则。
    check = can_lend(item["status"], active, due_date=body.due_date, business_date=business_date)
    if not check["ok"]:
        c.close(); raise HTTPException(409, check["reason"])
    cur = c.execute(
        "INSERT INTO loans(item_id,borrower,status,due_date,lent_at) VALUES (?,?,?,?,?)",
        (iid, body.borrower, "active", body.due_date, datetime.now(timezone.utc).isoformat()))
    c.execute("UPDATE items SET status='on_loan' WHERE id=?", (iid,))
    c.commit(); lid = cur.lastrowid; c.close(); return {"loan_id": lid}


class LendPreviewIn(BaseModel):
    due_date: str


@app.post("/api/items/{iid}/lend-preview")
def lend_preview(iid: int, body: LendPreviewIn):
    c = connect()
    business_date = _business_date(c)
    item = c.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
    if not item: c.close(); raise HTTPException(404, "item")
    active = c.execute("SELECT COUNT(*) c FROM loans WHERE item_id=? AND status='active'", (iid,)).fetchone()["c"]
    check = can_lend(item["status"], active, due_date=body.due_date, business_date=business_date)
    c.close()
    return {"ok": check["ok"], "reason": check["reason"], "business_date": business_date}


@app.post("/api/loans/{lid}/return")
def return_loan(lid: int):
    c = connect()
    loan = c.execute("SELECT * FROM loans WHERE id=?", (lid,)).fetchone()
    if not loan: c.close(); raise HTTPException(404, "loan")
    if loan["status"] != "active":
        c.close(); raise HTTPException(400, "not_active")
    c.execute("UPDATE loans SET status='returned', returned_at=? WHERE id=?",
              (datetime.now(timezone.utc).isoformat(), lid))
    c.execute("UPDATE items SET status='available' WHERE id=?", (loan["item_id"],))
    c.commit(); c.close(); return {"ok": True}


@app.get("/api/loans")
def loans():
    c = connect()
    snap = _loans_snapshot(c, _business_date(c))
    c.close()
    return snap


@app.get("/api/settings")
def settings():
    c = connect(); rows = _settings(c); c.close(); return rows


class SettingsIn(BaseModel):
    business_date: str | None = None


@app.post("/api/settings")
def save_settings(body: SettingsIn):
    # 非法业务日：直接拒绝，设置与顶细条都停留在改之前，不落任何库。
    new_date = body.business_date
    if new_date is None or parse_iso_date(new_date) is None:
        raise HTTPException(400, "invalid_business_date")
    c = connect()
    old_date = _business_date(c)
    if new_date == old_date:
        # 日期未变也要回同一套快照，避免界面各栏各过一套。
        snap = {"settings": _settings(c), "board": _board_snapshot(c, old_date), "loans": _loans_snapshot(c, old_date)}
        c.close()
        return snap
    c.execute(
        "INSERT INTO settings(key,value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (BUSINESS_DATE_KEY, new_date))
    c.commit()
    # 改判规则即“按新业务日重新分类”：顶细条、分栏、借还记录一次全部由
    # 保存后的同一快照派生，禁止出现顶条已不逾期、在借栏仍画逾期。
    snap = {"settings": _settings(c), "board": _board_snapshot(c, new_date), "loans": _loans_snapshot(c, new_date)}
    c.close()
    return snap
