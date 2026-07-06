"""
Spark Expense Engine — pending invoice-line store.
==================================================
When a contractor submits an INVOICE (a self-prepared expense summary, not
receipts), the substantiation policy holds its big-ticket lines — lodging,
airfare, or any line at/over the receipt threshold — out of reimbursement until
the underlying RECEIPT is provided (see config/expense-rules.json ->
substantiation). Because of byte-hash dedup, the invoice is processed once and
then never re-appears in a later run, so a held line would otherwise vanish.

This store persists those held lines so that:
  1. they stay visible across runs ("awaiting receipts" digest), and
  2. when a matching receipt shows up in a later run, the line is auto-released.

Unit of tracking = one held INVOICE LINE. Id is
"<contractor_id>|<invoice_number>|<seq>" so re-processing the same invoice is
idempotent.

Release rule (Brandon, 2026-07-05): reimburse the INVOICE's (allocated) amount,
using the receipt only as proof. For split/shared costs (e.g. airfare billed
50% to this project, 50% to another payer) the receipt shows the full fare but
only the invoice-billed portion is owed by this project. Matches where the
receipt amount differs from the invoice amount are flagged for review.

File: pending_invoices.json (project root, gitignored like ledger.json).
Plain stdlib (json + datetime + re). Imported by the processor and dashboard.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PENDING_PATH = ROOT / "pending_invoices.json"

ALLOCATION_KEYWORDS = ("shared", "split", "allocat", "portion", "%", "50/50", "half")


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def load_pending(path: Path | None = None) -> list[dict]:
    path = path or PENDING_PATH
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("lines", [])


def save_pending(lines: list[dict], path: Path | None = None) -> None:
    path = path or PENDING_PATH
    payload = {
        "_comment": "Invoice lines held awaiting receipts (Spark Expense Engine). "
                    "status=awaiting_receipt means Spark is NOT paying it yet; "
                    "receipt_matched means a receipt arrived and it was released at the "
                    "invoice-billed (allocated) amount. Gitignored.",
        "lines": lines,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def line_id(contractor_id: str, invoice_number: str | None, seq: int) -> str:
    return f"{contractor_id}|{invoice_number or 'noinv'}|{seq}"


def looks_allocated(invoice_note: str | None) -> bool:
    """True if the invoice note signals a shared/split/allocated cost."""
    if not invoice_note:
        return False
    n = invoice_note.lower()
    return any(k in n for k in ALLOCATION_KEYWORDS)


def _norm_tokens(name: str | None) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", (name or "").lower()) if len(w) >= 4}


def _merchant_match(a: str | None, b: str | None) -> bool:
    """Loose merchant match: share a meaningful token (e.g. 'united', 'hyatt')."""
    return bool(_norm_tokens(a) & _norm_tokens(b))


def _date_close(d1: str | None, d2: str | None, days: int = 3) -> bool:
    if not d1 or not d2:
        return False
    try:
        return abs((date.fromisoformat(d1) - date.fromisoformat(d2)).days) <= days
    except ValueError:
        return d1 == d2


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

def upsert_pending_line(
    lines: list[dict],
    *,
    contractor_id: str,
    contractor_name: str,
    project_id: str | None,
    invoice_number: str | None,
    invoice_sha256: str | None,
    date_str: str | None,
    merchant: str | None,
    category: str | None,
    amount: float,
    invoice_note: str | None,
    seq: int,
    created_date: str | None = None,
) -> dict:
    """Record a held invoice line if not already tracked.

    Idempotent by id: if the line already exists (including if already matched),
    it is returned untouched so a re-processed invoice never resurrects a
    released line or duplicates it.
    """
    lid = line_id(contractor_id, invoice_number, seq)
    for l in lines:
        if l["id"] == lid:
            return l
    entry = {
        "id": lid,
        "contractor_id": contractor_id,
        "contractor_name": contractor_name,
        "project_id": project_id,
        "invoice_number": invoice_number,
        "invoice_sha256": invoice_sha256,
        "date": date_str,
        "merchant": merchant,
        "category": category,
        "amount": round(float(amount or 0), 2),
        "invoice_note": invoice_note,
        "is_allocated": looks_allocated(invoice_note),
        "status": "awaiting_receipt",
        "created_date": created_date or date.today().isoformat(),
        "matched_receipt": None,
        "released_amount": None,
        "matched_date": None,
    }
    lines.append(entry)
    return entry


def find_match(awaiting_lines: list[dict], receipt_row: dict) -> dict | None:
    """Find the awaiting held line a receipt row substantiates, or None.

    Match on contractor + merchant token overlap + date proximity (NOT amount,
    because allocated lines are billed at a fraction of the receipt total).
    Prefers same category, then the closest date.
    """
    cid = receipt_row.get("contractor_id")
    rm = receipt_row.get("merchant")
    rd = receipt_row.get("date")
    rcat = receipt_row.get("category")

    candidates = [
        l for l in awaiting_lines
        if l.get("contractor_id") == cid
        and _merchant_match(l.get("merchant"), rm)
        and _date_close(l.get("date"), rd)
    ]
    if not candidates:
        return None

    def _key(l):
        same_cat = 0 if l.get("category") == rcat else 1
        try:
            gap = abs((date.fromisoformat(l["date"]) - date.fromisoformat(rd)).days)
        except (ValueError, TypeError):
            gap = 999
        return (same_cat, gap)

    return sorted(candidates, key=_key)[0]


def mark_matched(
    line: dict,
    *,
    receipt_sha: str | None,
    receipt_merchant: str | None,
    receipt_date: str | None,
    receipt_amount: float | None,
    matched_date: str | None = None,
) -> None:
    """Release a held line: it is now substantiated by a receipt. The released
    amount is the INVOICE's (allocated) amount, not the receipt amount."""
    line["status"] = "receipt_matched"
    line["matched_receipt"] = {
        "sha256": receipt_sha,
        "merchant": receipt_merchant,
        "date": receipt_date,
        "receipt_amount": None if receipt_amount is None else round(float(receipt_amount), 2),
    }
    line["released_amount"] = round(float(line.get("amount") or 0), 2)
    line["matched_date"] = matched_date or date.today().isoformat()


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def awaiting(lines: list[dict]) -> list[dict]:
    return [l for l in lines if l.get("status") == "awaiting_receipt"]


def total_awaiting(lines: list[dict]) -> float:
    return round(sum(float(l.get("amount") or 0) for l in awaiting(lines)), 2)


def _age_days(created_date: str | None, today: date | None = None) -> int:
    if not created_date:
        return 0
    today = today or date.today()
    try:
        return (today - date.fromisoformat(created_date)).days
    except ValueError:
        return 0


def awaiting_by_contractor(lines: list[dict], today: date | None = None) -> list[dict]:
    """Aggregate awaiting held amounts per contractor (largest first)."""
    today = today or date.today()
    by: dict[str, dict] = {}
    for l in awaiting(lines):
        k = l["contractor_id"]
        agg = by.setdefault(k, {
            "contractor_id": k,
            "contractor_name": l.get("contractor_name") or k,
            "total_usd": 0.0,
            "n_lines": 0,
            "oldest_date": l.get("created_date"),
        })
        agg["total_usd"] += float(l.get("amount") or 0)
        agg["n_lines"] += 1
        if (l.get("created_date") or "9999") < (agg["oldest_date"] or "9999"):
            agg["oldest_date"] = l.get("created_date")

    result = []
    for agg in by.values():
        agg["total_usd"] = round(agg["total_usd"], 2)
        agg["oldest_age_days"] = _age_days(agg["oldest_date"], today)
        result.append(agg)
    return sorted(result, key=lambda a: a["total_usd"], reverse=True)
