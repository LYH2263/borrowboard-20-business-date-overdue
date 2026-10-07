from datetime import date, datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.db import connect
from app.engines.borrow_rules import (
    BUSINESS_DATE_KEY, can_lend, classify_loans, effective_business_date, parse_business_date,
)

app = FastAPI(title="Borrowboard", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

@app.get("/api/health")
def health(): return {"ok": True, "project": "borrowboard"}

def _settings_map(c):
    return {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}

def _business_date(c):
    """The date overdue is measured against. Saved setting wins; a missing
    or corrupted value falls back to the machine date but is never saved."""
    raw = c.execute("SELECT value FROM settings WHERE key=?", (BUSINESS_DATE_KEY,)).fetchone()
    return effective_business_date(raw["value"] if raw else None, date.today().isoformat())

def _board_payload(c):
    # One read of the business date feeds the stat bar and every pane, so the
    # top strip and the columns can never disagree about which day applies.
    bdate = _business_date(c)
    available = [dict(r) for r in c.execute("SELECT * FROM items WHERE status='available'")]
    loans = [dict(r) for r in c.execute(
        """SELECT loans.*, items.title FROM loans JOIN items ON items.id=loans.item_id
           WHERE loans.status='active'""")]
    cls = classify_loans(loans, bdate)
    return {
        BUSINESS_DATE_KEY: bdate,
        "available": available,
        "active": cls["active"],
        "overdue": cls["overdue"],
        "counts": {"available": len(available), "active": len(cls["active"]), "overdue": len(cls["overdue"])},
    }

@app.get("/api/items")
def items():
    c = connect(); rows = [dict(r) for r in c.execute("SELECT * FROM items")]; c.close(); return rows

@app.get("/api/board")
def board():
    c = connect(); payload = _board_payload(c); c.close(); return payload

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
    # A preview may have been generated under an older business date.
    # Eligibility is re-judged at submit time from stored state, so preview
    # qualification, stat strip and available pane all follow today's rules.
    try:
        parse_business_date(body.due_date)
    except ValueError:
        raise HTTPException(400, "bad_due_date")
    c = connect()
    item = c.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
    if not item: c.close(); raise HTTPException(404, "item")
    active = c.execute("SELECT COUNT(*) c FROM loans WHERE item_id=? AND status='active'", (iid,)).fetchone()["c"]
    check = can_lend(item["status"], active)
    if not check["ok"]:
        c.close(); raise HTTPException(409, check["reason"])
    cur = c.execute(
        "INSERT INTO loans(item_id,borrower,status,due_date,lent_at) VALUES (?,?,?,?,?)",
        (iid, body.borrower, "active", body.due_date, datetime.now(timezone.utc).isoformat()))
    c.execute("UPDATE items SET status='on_loan' WHERE id=?", (iid,))
    c.commit(); lid = cur.lastrowid
    # Response is computed from the post-write state under the current date.
    payload = _board_payload(c)
    c.close()
    return {"loan_id": lid, "board": payload}

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
    bdate = _business_date(c)
    rows = [dict(r) for r in c.execute(
        "SELECT loans.*, items.title FROM loans JOIN items ON items.id=loans.item_id ORDER BY loans.id DESC")]
    c.close()
    payload = classify_loans(rows, bdate)
    payload[BUSINESS_DATE_KEY] = bdate
    return payload

@app.get("/api/settings")
def settings():
    c = connect(); rows = _settings_map(c)
    # The effective business date is always exposed, even before one is saved,
    # so the UI shows the date its overdue sections are actually using.
    rows.setdefault(BUSINESS_DATE_KEY, _business_date(c))
    c.close(); return rows

class SettingsIn(BaseModel):
    # Free-form settings map (board_name, business_date, ...).
    values: dict

def _settings_update(values: dict):
    """Validate then persist. An invalid business_date rejects the whole
    save (400) and leaves both the stored setting and every overdue verdict
    exactly as they were before the request."""
    if BUSINESS_DATE_KEY in values:
        try:
            parse_business_date(values[BUSINESS_DATE_KEY])
        except (TypeError, ValueError):
            raise HTTPException(400, "bad_business_date")
    c = connect()
    try:
        for key, value in values.items():
            c.execute(
                "INSERT INTO settings(key,value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value))
        c.commit()
    finally:
        c.close()

@app.put("/api/settings")
def save_settings(body: SettingsIn):
    _settings_update(body.values)
    # Return verdicts recomputed from the just-saved result in the same call:
    # stat strip, panes and loan history follow one saved business date.
    c = connect()
    settings_map = _settings_map(c)
    board_payload = _board_payload(c)
    bdate = board_payload[BUSINESS_DATE_KEY]
    rows = [dict(r) for r in c.execute(
        "SELECT loans.*, items.title FROM loans JOIN items ON items.id=loans.item_id ORDER BY loans.id DESC")]
    c.close()
    loans_payload = classify_loans(rows, bdate)
    loans_payload[BUSINESS_DATE_KEY] = bdate
    return {"settings": settings_map, "board": board_payload, "loans": loans_payload}
