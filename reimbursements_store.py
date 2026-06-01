"""
Spark Expense Engine — reimbursement claims store.
===================================================
Tracks WHAT SPARK OWES vs WHAT HAS BEEN PAID. The ledger (ledger.json) only
records that a receipt was *processed* (OCR'd); it has no notion of payment.
This store fills that gap so unpaid balances don't go invisible after their one
appearance in a weekly report.

Unit of tracking = a CLAIM: one contractor's reimbursable total for one weekly
run. Claim id is "<contractor_id>|<week_label>" so re-running the same week
updates the same claim instead of duplicating it.

File: reimbursements.json (project root, gitignored like ledger.json).

This module is plain stdlib (json + datetime) and is imported by both the
processor and the dashboard. Keep it I/O-light and dependency-free.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REIMBURSEMENTS_PATH = ROOT / "reimbursements.json"


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def load_claims(path: Path | None = None) -> list[dict]:
    path = path or REIMBURSEMENTS_PATH
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("claims", [])


def save_claims(claims: list[dict], path: Path | None = None) -> None:
    path = path or REIMBURSEMENTS_PATH
    payload = {
        "_comment": "Reimbursement claims for the Spark Expense Engine. "
                    "One claim = one contractor's reimbursable total for one weekly run. "
                    "reimbursed=false means Spark still owes this money. Gitignored.",
        "claims": claims,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

def claim_id(contractor_id: str, week_label: str) -> str:
    return f"{contractor_id}|{week_label}"


def upsert_claim(
    claims: list[dict],
    *,
    contractor_id: str,
    contractor_name: str,
    week_label: str,
    reimbursable_usd: float,
    receipt_shas: list[str],
    created_date: str | None = None,
) -> dict:
    """Create or update the claim for (contractor, week).

    If a claim already exists and is NOT yet reimbursed, the new receipts are
    ACCUMULATED onto it (a later run in the same week extracts only the newly
    added receipts — dedup skips the ones already processed — so we add this
    run's amount + receipts rather than replacing). Re-running with no genuinely
    new receipts is an idempotent no-op. If the claim is already reimbursed it is
    left untouched (a re-run must never un-pay a claim); the caller can detect
    that via the returned '_locked' marker.
    """
    cid = claim_id(contractor_id, week_label)
    created_date = created_date or date.today().isoformat()
    incoming = set(receipt_shas)

    for c in claims:
        if c["id"] == cid:
            if c.get("reimbursed"):
                # Already paid — don't disturb it.
                c["_locked"] = True
                return c
            existing = set(c.get("receipt_shas") or [])
            if incoming and incoming <= existing:
                # Nothing genuinely new this run — idempotent no-op.
                return c
            union = sorted(existing | incoming)
            c["reimbursable_usd"] = round(float(c.get("reimbursable_usd") or 0) + float(reimbursable_usd), 2)
            c["n_receipts"] = len(union)
            c["receipt_shas"] = union
            return c

    claim = {
        "id": cid,
        "contractor_id": contractor_id,
        "contractor_name": contractor_name,
        "week_label": week_label,
        "reimbursable_usd": round(float(reimbursable_usd), 2),
        "n_receipts": len(receipt_shas),
        "receipt_shas": receipt_shas,
        "created_date": created_date,
        "reimbursed": False,
        "reimbursed_date": None,
        "reference": None,
    }
    claims.append(claim)
    return claim


def mark_paid(
    claims: list[dict],
    cid: str,
    reimbursed_date: str | None = None,
    reference: str | None = None,
) -> bool:
    """Mark a claim reimbursed. Returns True if found + updated."""
    reimbursed_date = reimbursed_date or date.today().isoformat()
    for c in claims:
        if c["id"] == cid:
            c["reimbursed"] = True
            c["reimbursed_date"] = reimbursed_date
            c["reference"] = reference or None
            c.pop("_locked", None)
            return True
    return False


def mark_unpaid(claims: list[dict], cid: str) -> bool:
    """Undo a payment mark (in case it was clicked by mistake)."""
    for c in claims:
        if c["id"] == cid:
            c["reimbursed"] = False
            c["reimbursed_date"] = None
            c["reference"] = None
            return True
    return False


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def outstanding_claims(claims: list[dict]) -> list[dict]:
    """Unpaid claims with a positive balance, oldest first."""
    out = [c for c in claims if not c.get("reimbursed") and float(c.get("reimbursable_usd") or 0) > 0]
    return sorted(out, key=lambda c: (c.get("created_date") or "", c.get("contractor_name") or ""))


def _age_days(created_date: str | None, today: date | None = None) -> int:
    if not created_date:
        return 0
    today = today or date.today()
    try:
        return (today - date.fromisoformat(created_date)).days
    except ValueError:
        return 0


def outstanding_by_contractor(claims: list[dict], today: date | None = None) -> list[dict]:
    """Aggregate unpaid balances per contractor.

    Returns a list of dicts (largest balance first):
        {contractor_id, contractor_name, total_usd, n_claims, oldest_date, oldest_age_days}
    """
    today = today or date.today()
    by: dict[str, dict] = {}
    for c in outstanding_claims(claims):
        k = c["contractor_id"]
        agg = by.setdefault(k, {
            "contractor_id": k,
            "contractor_name": c.get("contractor_name") or k,
            "total_usd": 0.0,
            "n_claims": 0,
            "oldest_date": c.get("created_date"),
        })
        agg["total_usd"] += float(c.get("reimbursable_usd") or 0)
        agg["n_claims"] += 1
        if (c.get("created_date") or "9999") < (agg["oldest_date"] or "9999"):
            agg["oldest_date"] = c.get("created_date")

    result = []
    for agg in by.values():
        agg["total_usd"] = round(agg["total_usd"], 2)
        agg["oldest_age_days"] = _age_days(agg["oldest_date"], today)
        result.append(agg)
    return sorted(result, key=lambda a: a["total_usd"], reverse=True)


def total_outstanding(claims: list[dict]) -> float:
    return round(sum(float(c.get("reimbursable_usd") or 0) for c in outstanding_claims(claims)), 2)
