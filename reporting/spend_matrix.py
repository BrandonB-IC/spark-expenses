"""
Spark Expense Engine — spend-by-project x person aggregator.
============================================================
Answers "who spent what against which project" by combining the three
cumulative stores:

  - reimbursements.json (claims): the authoritative reimbursable total per
    contractor-week + paid/unpaid status. This is the money Spark owes or has
    paid. Claims have receipt_shas but no project breakdown of their own.
  - ledger.json: maps each receipt sha -> (contractor, project, extracted$).
    Used to attribute a claim across the project(s) its receipts belong to.
  - pending_invoices.json: invoice lines held awaiting receipts, with an
    explicit project_id — money not yet owed (pending verification).

Each matrix cell (project x person) splits into three buckets:
  reimbursed   — claim marked paid
  outstanding  — claim unpaid (verified, owed)
  pending      — held invoice line awaiting a receipt (not yet owed)

Attribution note: a claim can span multiple projects (e.g. a week mixing NDL and
WHI receipts). Its reimbursable total is split across those projects in
proportion to the ledger's extracted amount per project. That is an
approximation — the post-rules reimbursable differs slightly from raw extracted
because of per-diem/substantiation/allocation — but it is faithful for an
overview because the large line items dominate both numbers. Single-project
claims (the common case) are attributed exactly.

PURE FUNCTIONS + thin loaders. No external deps.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = ROOT / "ledger.json"
REIMBURSEMENTS_PATH = ROOT / "reimbursements.json"
PENDING_PATH = ROOT / "pending_invoices.json"
CONTRACTORS_PATH = ROOT / "config" / "contractors.json"

BUCKETS = ("reimbursed", "outstanding", "pending")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_sources() -> dict:
    ledger = _load_json(LEDGER_PATH, {})
    claims = _load_json(REIMBURSEMENTS_PATH, {}).get("claims", [])
    pending = _load_json(PENDING_PATH, {}).get("lines", [])
    contractors = _load_json(CONTRACTORS_PATH, {}).get("contractors", [])
    names = {c["id"]: (c.get("display_name") or c["id"]) for c in contractors}
    return {"ledger": ledger, "claims": claims, "pending": pending, "names": names}


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------

def _claim_project_split(claim: dict, ledger: dict) -> dict:
    """Return {project_id: fraction} for how a claim's reimbursable splits by
    project, using the ledger's extracted amount per project as weights."""
    by_project: dict[str, float] = {}
    for sha in claim.get("receipt_shas") or []:
        entry = ledger.get(sha)
        if not entry:
            continue
        proj = entry.get("project_id") or "(unassigned)"
        by_project[proj] = by_project.get(proj, 0.0) + float(entry.get("extracted_total_usd") or 0)

    if not by_project:
        return {"(unassigned)": 1.0}

    total = sum(by_project.values())
    if total <= 0:
        # Extracted totals are all zero — split evenly across the projects seen.
        frac = 1.0 / len(by_project)
        return {p: frac for p in by_project}
    return {p: v / total for p, v in by_project.items()}


def _blank_bucket() -> dict:
    return {b: 0.0 for b in BUCKETS}


def build_matrix(ledger: dict, claims: list[dict], pending: list[dict], names: dict | None = None) -> dict:
    """Build the project x person spend matrix. See module docstring for buckets."""
    names = names or {}
    cells: dict[tuple[str, str], dict] = {}
    projects: set[str] = set()
    people: set[str] = set()

    def _cell(project: str, person: str) -> dict:
        projects.add(project)
        people.add(person)
        return cells.setdefault((project, person), _blank_bucket())

    # Claims -> reimbursed / outstanding, split across projects.
    for c in claims:
        person = c.get("contractor_id")
        amount = float(c.get("reimbursable_usd") or 0)
        if amount <= 0:
            continue
        bucket = "reimbursed" if c.get("reimbursed") else "outstanding"
        for proj, frac in _claim_project_split(c, ledger).items():
            _cell(proj, person)[bucket] += amount * frac

    # Pending held invoice lines -> pending bucket, by explicit project.
    for l in pending:
        if l.get("status") != "awaiting_receipt":
            continue
        person = l.get("contractor_id")
        proj = l.get("project_id") or "(unassigned)"
        _cell(proj, person)["pending"] += float(l.get("amount") or 0)

    # Round + add totals per cell.
    for cell in cells.values():
        for b in BUCKETS:
            cell[b] = round(cell[b], 2)
        cell["total"] = round(sum(cell[b] for b in BUCKETS), 2)

    projects_sorted = sorted(projects)
    people_sorted = sorted(people, key=lambda p: names.get(p, p).lower())

    def _sum(items) -> dict:
        agg = _blank_bucket()
        for it in items:
            for b in BUCKETS:
                agg[b] += it.get(b, 0.0)
        for b in BUCKETS:
            agg[b] = round(agg[b], 2)
        agg["total"] = round(sum(agg[b] for b in BUCKETS), 2)
        return agg

    project_totals = {p: _sum([cells[(p, q)] for q in people_sorted if (p, q) in cells]) for p in projects_sorted}
    person_totals = {q: _sum([cells[(p, q)] for p in projects_sorted if (p, q) in cells]) for q in people_sorted}
    grand = _sum(list(cells.values()))

    return {
        "projects": projects_sorted,
        "people": people_sorted,
        "names": {q: names.get(q, q) for q in people_sorted},
        "cells": {f"{p}||{q}": v for (p, q), v in cells.items()},
        "project_totals": project_totals,
        "person_totals": person_totals,
        "grand": grand,
    }


def cell(matrix: dict, project: str, person: str) -> dict:
    return matrix["cells"].get(f"{project}||{person}") or {**_blank_bucket(), "total": 0.0}
