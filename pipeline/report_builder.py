"""
Report builder for the Spark Expense Engine.

Takes the output of rules_engine.classify() and produces:
  - summary.md  : human-readable Markdown dashboard (for email + dashboard view)
  - ledger.csv  : flat CSV with one row per receipt (for accounting import)

The audit packet PDF (merged receipt images) is a separate concern handled in
Phase 4 alongside the scheduler — it requires downloading + paginating the
original files, which is I/O-heavy and slower than the in-memory work here.

PURE FUNCTIONS — takes dicts in, returns strings out. Caller writes to disk.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------

def _money(v: Optional[float]) -> str:
    if v is None:
        return "—"
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_flag_reasons(reasons: list[str]) -> str:
    if not reasons:
        return ""
    return "; ".join(reasons)


def build_markdown_summary(
    classified: dict,
    contractor: dict,
    project_filter: Optional[str] = None,
    week_label: Optional[str] = None,
) -> str:
    """Build a Markdown report for one contractor's classified receipts."""
    receipts = classified["receipts"]
    summary = classified["summary"]
    warnings = classified.get("warnings", [])

    contractor_name = contractor.get("display_name") or contractor.get("id") or "Unknown"
    today = datetime.now().strftime("%Y-%m-%d")
    week_str = f" — {week_label}" if week_label else ""
    project_str = f" — {project_filter}" if project_filter else ""

    lines = []
    lines.append(f"# Spark Expense Report: {contractor_name}{week_str}{project_str}")
    lines.append("")
    lines.append(f"_Generated {today}_")
    lines.append("")

    # ---- Warnings (top of page so they aren't missed) ----
    if warnings:
        lines.append("## Warnings")
        for w in warnings:
            lines.append(f"- **NOTE:** {w}")
        lines.append("")

    # ---- Headline numbers ----
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Total extracted from receipts | {_money(summary['total_extracted'])} |")
    lines.append(f"| Total reimbursable | **{_money(summary['total_reimbursable'])}** |")
    lines.append(f"| Travel days detected | {summary['n_travel_days']} ({', '.join(summary['travel_days']) or '—'}) |")
    lines.append(f"| Per-diem added | {_money(summary['total_per_diem_added'])} |")
    lines.append(f"| Replaced by per-diem | {_money(summary['total_replaced_by_per_diem'])} |")
    lines.append(f"| Net per-diem impact | {_money(summary['net_per_diem_impact'])} |")
    lines.append(f"| Items flagged for review | {summary['flag_count']} ({_money(summary['flagged_amount'])}) |")
    lines.append("")

    # ---- Flagged items first (most important) ----
    flagged = [r for r in receipts if r.get("flagged")]
    if flagged:
        lines.append("## Flagged for Review")
        lines.append("")
        lines.append("| Date | Merchant | Amount | Reasons |")
        lines.append("|---|---|---:|---|")
        for r in sorted(flagged, key=lambda x: (x.get("date") or "", x.get("merchant") or "")):
            lines.append(
                f"| {r.get('date') or '?'} "
                f"| {r.get('merchant') or '?'} "
                f"| {_money(r.get('amount'))} "
                f"| {_fmt_flag_reasons(r.get('flag_reasons') or [])} |"
            )
        lines.append("")

    # ---- All approved items grouped by category ----
    lines.append("## Approved Items")
    lines.append("")

    by_category: dict[str, list[dict]] = {}
    for r in receipts:
        cat = r.get("category") or "uncategorized"
        by_category.setdefault(cat, []).append(r)

    # Order categories: per-diem first (synthetic), then airfare/hotel/transport, then meals, then other
    category_order = [
        "per-diem",
        "travel-airfare",
        "travel-hotel",
        "travel-rideshare",
        "travel-other",
        "meals",
        "supplies",
        "fees",
        "other",
        "uncategorized",
    ]
    sorted_cats = sorted(
        by_category.keys(),
        key=lambda c: (category_order.index(c) if c in category_order else 999, c),
    )

    for cat in sorted_cats:
        rows = by_category[cat]
        cat_total_reimb = sum(float(r.get("reimbursable_amount") or 0) for r in rows)
        cat_total_orig = sum(float(r.get("amount") or 0) for r in rows)
        lines.append(f"### {cat} — {_money(cat_total_reimb)} reimbursable")
        lines.append("")
        lines.append("| Date | Merchant | Original | Reimbursable | Notes |")
        lines.append("|---|---|---:|---:|---|")
        for r in sorted(rows, key=lambda x: (x.get("date") or "", x.get("merchant") or "")):
            note_parts = []
            if r.get("per_diem_synthetic"):
                note_parts.append("Auto per-diem")
            if r.get("replaced_by_per_diem"):
                note_parts.append("Replaced by per-diem")
            if r.get("notes"):
                note_parts.append(str(r["notes"]))
            note_str = " · ".join(note_parts)
            # Truncate long notes for readability in the markdown table
            if len(note_str) > 140:
                note_str = note_str[:137] + "..."
            lines.append(
                f"| {r.get('date') or '?'} "
                f"| {(r.get('merchant') or '?')[:40]} "
                f"| {_money(r.get('amount'))} "
                f"| {_money(r.get('reimbursable_amount'))} "
                f"| {note_str} |"
            )
        if cat_total_reimb != cat_total_orig:
            lines.append(f"| | _subtotal_ | {_money(cat_total_orig)} | **{_money(cat_total_reimb)}** | |")
        lines.append("")

    # ---- Footer ----
    lines.append("---")
    lines.append("")
    lines.append(
        f"_Generated by Spark Expense Engine. Rules version: "
        f"`{classified.get('rules_version', 'unknown')}`. "
        f"Reply to this email or open the dashboard at http://localhost:8770 to approve or flag items._"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSV ledger
# ---------------------------------------------------------------------------

CSV_FIELDS = [
    "date",
    "contractor",
    "project",
    "category",
    "merchant",
    "merchant_location",
    "currency",
    "amount",
    "reimbursable_amount",
    "subtotal",
    "tax",
    "tip",
    "itemization_status",
    "flagged",
    "flag_reasons",
    "replaced_by_per_diem",
    "per_diem_synthetic",
    "drive_path",
    "sha256",
    "notes",
]


def build_csv_ledger(
    receipts: list[dict],
    contractor_id: str,
) -> str:
    """Build a flat CSV ledger string suitable for import into accounting software."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for r in receipts:
        row = {k: r.get(k) for k in CSV_FIELDS}
        row["contractor"] = contractor_id
        row["project"] = r.get("project_id")  # may be None for synthetic
        # flag_reasons is a list — join into a single cell
        if isinstance(row.get("flag_reasons"), list):
            row["flag_reasons"] = " | ".join(row["flag_reasons"])
        writer.writerow(row)
    return buf.getvalue()
