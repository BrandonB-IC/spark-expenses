"""
Spark Expense Engine — standalone spend-overview HTML.
======================================================
Renders a self-contained (inline CSS, no external assets) HTML page answering
"who spent what against which project," from the spend_matrix aggregator.

  python reporting/build_spend_overview.py            # -> reports/spend-overview.html

Also called at the end of the weekly run so the file stays current. Open the
file directly in a browser; nothing external is loaded.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reporting.spend_matrix import load_sources, build_matrix, cell, BUCKETS

OUTPUT_PATH = ROOT / "reports" / "spend-overview.html"

# Spark palette
GREEN = "#16A34A"    # reimbursed / paid
BLUE = "#2B7BB5"     # outstanding / owed
AMBER = "#D9822B"    # pending / awaiting receipts
CHARCOAL = "#252525"
BUCKET_COLOR = {"reimbursed": GREEN, "outstanding": BLUE, "pending": AMBER}
BUCKET_LABEL = {
    "reimbursed": "Reimbursed (paid)",
    "outstanding": "Outstanding (owed)",
    "pending": "Awaiting receipts",
}


def _money(v: float) -> str:
    return "$" + f"{float(v or 0):,.2f}"


def _money0(v: float) -> str:
    return "$" + f"{float(v or 0):,.0f}"


def _bar(bucket_vals: dict, total: float) -> str:
    """A thin stacked bar showing the 3-way split within a cell."""
    if not total:
        return '<div class="bar empty"></div>'
    segs = []
    for b in BUCKETS:
        pct = (bucket_vals.get(b, 0.0) / total) * 100 if total else 0
        if pct > 0:
            segs.append(f'<span style="width:{pct:.4f}%;background:{BUCKET_COLOR[b]}"></span>')
    return '<div class="bar">' + "".join(segs) + "</div>"


def _cell_html(c: dict) -> str:
    total = c.get("total", 0.0)
    if not total:
        return '<td class="cell zero">—</td>'
    tip = " · ".join(
        f"{BUCKET_LABEL[b]}: {_money(c.get(b, 0))}" for b in BUCKETS if c.get(b, 0)
    )
    return (
        f'<td class="cell" title="{escape(tip)}">'
        f'<div class="amt">{_money0(total)}</div>'
        f"{_bar(c, total)}"
        f"</td>"
    )


def _totals_row_cells(totals: dict) -> str:
    return (
        f'<div class="amt">{_money0(totals.get("total", 0))}</div>'
        f'{_bar(totals, totals.get("total", 0))}'
    )


def render_html(matrix: dict, generated: str) -> str:
    projects = matrix["projects"]
    people = matrix["people"]
    names = matrix["names"]
    grand = matrix["grand"]

    # Summary cards
    cards = []
    for b in BUCKETS:
        cards.append(
            f'<div class="card"><div class="card-dot" style="background:{BUCKET_COLOR[b]}"></div>'
            f'<div class="card-label">{BUCKET_LABEL[b]}</div>'
            f'<div class="card-value">{_money(grand.get(b, 0))}</div></div>'
        )
    cards.append(
        f'<div class="card total"><div class="card-label">Total tracked</div>'
        f'<div class="card-value">{_money(grand.get("total", 0))}</div></div>'
    )

    # Matrix header
    head_cells = "".join(f'<th class="person">{escape(names[q])}</th>' for q in people)
    # Matrix body
    body_rows = []
    for p in projects:
        row_cells = "".join(_cell_html(cell(matrix, p, q)) for q in people)
        pt = matrix["project_totals"][p]
        body_rows.append(
            f'<tr><th class="proj">{escape(p)}</th>{row_cells}'
            f'<td class="cell rowtot">{_totals_row_cells(pt)}</td></tr>'
        )
    # Totals row
    col_tot_cells = "".join(
        f'<td class="cell coltot">{_totals_row_cells(matrix["person_totals"][q])}</td>'
        for q in people
    )
    grand_cell = f'<td class="cell grandtot">{_totals_row_cells(grand)}</td>'

    legend = "".join(
        f'<span class="lg"><span class="sw" style="background:{BUCKET_COLOR[b]}"></span>{BUCKET_LABEL[b]}</span>'
        for b in BUCKETS
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Spark Expenses — Spend Overview</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: {CHARCOAL}; margin: 0; background: #f6f7f9; }}
  .wrap {{ max-width: 1040px; margin: 0 auto; padding: 32px 24px 60px; }}
  header h1 {{ font-size: 24px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  header .sub {{ color: #6b7280; font-size: 13px; margin-bottom: 24px; }}
  .accent {{ color: {GREEN}; }}
  .cards {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 28px; }}
  .card {{ background: #fff; border: 1px solid #e6e8eb; border-radius: 10px; padding: 14px 16px;
    flex: 1 1 180px; position: relative; }}
  .card.total {{ background: {CHARCOAL}; color: #fff; }}
  .card-dot {{ width: 10px; height: 10px; border-radius: 50%; position: absolute; top: 16px; right: 14px; }}
  .card-label {{ font-size: 12px; color: #6b7280; }}
  .card.total .card-label {{ color: #c9ccd1; }}
  .card-value {{ font-size: 21px; font-weight: 650; margin-top: 4px; letter-spacing: -0.01em; }}
  .scroll {{ overflow-x: auto; background: #fff; border: 1px solid #e6e8eb; border-radius: 10px; }}
  table {{ border-collapse: collapse; width: 100%; min-width: 620px; }}
  th, td {{ padding: 12px 14px; text-align: right; }}
  thead th {{ font-size: 12px; color: #6b7280; font-weight: 600; border-bottom: 1px solid #e6e8eb;
    background: #fbfbfc; }}
  thead th.corner {{ text-align: left; }}
  th.proj {{ text-align: left; font-size: 13px; font-weight: 600; white-space: nowrap; }}
  tbody tr {{ border-bottom: 1px solid #f0f1f3; }}
  tbody tr:last-child td, tbody tr:last-child th {{ border-bottom: none; }}
  .cell .amt {{ font-size: 14px; font-weight: 550; font-variant-numeric: tabular-nums; }}
  .cell.zero {{ color: #c4c8ce; }}
  .bar {{ display: flex; height: 5px; border-radius: 3px; overflow: hidden; margin-top: 5px;
    background: #eef0f2; }}
  .bar span {{ display: block; height: 100%; }}
  .bar.empty {{ visibility: hidden; }}
  tr.totals {{ background: #fbfbfc; border-top: 2px solid #e6e8eb; }}
  tr.totals th, .rowtot, .coltot, .grandtot {{ font-weight: 700; }}
  .rowtot, .coltot {{ background: #fbfbfc; }}
  .grandtot {{ background: #f2f4f6; }}
  .legend {{ margin: 16px 2px 0; display: flex; gap: 18px; flex-wrap: wrap; font-size: 12px; color: #4b5563; }}
  .lg {{ display: inline-flex; align-items: center; gap: 6px; }}
  .sw {{ width: 11px; height: 11px; border-radius: 3px; display: inline-block; }}
  .note {{ font-size: 12px; color: #8b9099; margin-top: 22px; line-height: 1.5; }}
</style></head>
<body><div class="wrap">
<header>
  <h1><span class="accent">Spark</span> Expenses — Spend Overview</h1>
  <div class="sub">Who spent what against which project · generated {escape(generated)}</div>
</header>

<div class="cards">{''.join(cards)}</div>

<div class="scroll"><table>
  <thead><tr><th class="corner">Project</th>{head_cells}<th class="person">Total</th></tr></thead>
  <tbody>
    {''.join(body_rows)}
    <tr class="totals"><th class="proj">Total</th>{col_tot_cells}{grand_cell}</tr>
  </tbody>
</table></div>

<div class="legend">{legend}</div>

<p class="note">
  Amounts are reimbursable dollars (what Spark pays), not gross receipts. Each cell's bar shows its
  split across the three states. <strong>Outstanding</strong> is verified and owed; <strong>reimbursed</strong>
  has been paid; <strong>awaiting receipts</strong> are invoice lines held pending substantiation (not yet owed).
  Where a weekly claim spans more than one project, its total is attributed across projects in proportion to the
  ledger's extracted amount per project (an estimate for multi-project weeks; single-project weeks are exact).
</p>
</div></body></html>
"""


def generate(output_path: Path | None = None, generated: str | None = None) -> Path:
    output_path = output_path or OUTPUT_PATH
    generated = generated or datetime.now().strftime("%Y-%m-%d %H:%M")
    s = load_sources()
    matrix = build_matrix(s["ledger"], s["claims"], s["pending"], s["names"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(matrix, generated), encoding="utf-8")
    return output_path


def main() -> None:
    path = generate()
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
