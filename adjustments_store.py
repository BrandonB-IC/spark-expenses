"""
Spark Expense Engine — per-receipt adjustments store.
=====================================================
A manual correction/override layer on top of the extracted amounts, keyed by a
receipt's SHA-256 (the same id the ledger uses). Handles the cases the OCR +
rules cannot decide on their own:

  - override : reimburse a specific amount instead of the extracted total
               (e.g. a hotel folio spanning 2 nights where only 1 is business;
               a corrected OCR misread).
  - void     : do not reimburse this receipt at all (e.g. a duplicate, or a
               personal charge uploaded by mistake).

Every adjustment carries a human reason for the audit trail. Adjustments are
applied wherever a receipt's reimbursable amount is computed (claims rebuild,
and new-receipt processing via reimbursable_override).

File: adjustments.json (project root, gitignored). Plain stdlib.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADJUSTMENTS_PATH = ROOT / "adjustments.json"


def load_adjustments(path: Path | None = None) -> dict:
    path = path or ADJUSTMENTS_PATH
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("adjustments", {})


def save_adjustments(adjustments: dict, path: Path | None = None) -> None:
    path = path or ADJUSTMENTS_PATH
    payload = {
        "_comment": "Per-receipt corrections for the Spark Expense Engine, keyed by SHA-256. "
                    "type 'override' reimburses `amount` instead of the extracted total; "
                    "type 'void' reimburses nothing. Every entry has a reason. Gitignored.",
        "adjustments": adjustments,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def set_override(adjustments: dict, sha: str, amount: float, reason: str,
                 created_date: str | None = None) -> dict:
    adjustments[sha] = {
        "type": "override",
        "amount": round(float(amount), 2),
        "reason": reason,
        "created_date": created_date or date.today().isoformat(),
    }
    return adjustments[sha]


def set_void(adjustments: dict, sha: str, reason: str, created_date: str | None = None) -> dict:
    adjustments[sha] = {
        "type": "void",
        "amount": 0.0,
        "reason": reason,
        "created_date": created_date or date.today().isoformat(),
    }
    return adjustments[sha]


def remove(adjustments: dict, sha: str) -> bool:
    return adjustments.pop(sha, None) is not None


def adjusted_amount(adjustments: dict, sha: str, base_amount: float) -> float:
    """Return the effective reimbursable amount for a receipt after adjustments."""
    adj = adjustments.get(sha)
    if not adj:
        return float(base_amount or 0)
    if adj.get("type") == "void":
        return 0.0
    if adj.get("type") == "override":
        return round(float(adj.get("amount") or 0), 2)
    return float(base_amount or 0)
