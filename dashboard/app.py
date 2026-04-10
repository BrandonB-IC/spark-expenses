"""
Spark Expense Engine — standalone Flask dashboard.

Runs on http://localhost:8770 (separate from EA's 8765).

Pages:
  /              - Index: latest report card + history
  /report/<week> - Per-week report view (rendered markdown)
  /rules         - Read-only rules + changelog
  /contractors   - Read-only contractor list
  /run           - POST: spawn the expense_processor as a subprocess
  /status        - GET: returns whether a run is in progress + last run timestamp

Design notes:
- The "Run Now" button POSTs to /run, which spawns scheduler/expense_processor.py
  as a detached subprocess and returns immediately. The dashboard polls /status
  to know when it's done.
- Markdown -> HTML conversion uses the `markdown` library with the `tables`
  extension.
- All data is read-only from the dashboard's perspective EXCEPT triggering a
  run. We do NOT let the dashboard mutate ledger.json, rules, or contractors.
  Edits happen by editing the JSON files directly (per Brandon's preference).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

REPORTS_DIR = ROOT / "reports"
LEDGER_PATH = ROOT / "ledger.json"
RULES_PATH = ROOT / "config" / "expense-rules.json"
CHANGELOG_PATH = ROOT / "config" / "expense-rules-changelog.md"
CONTRACTORS_PATH = ROOT / "config" / "contractors.json"
PROJECTS_PATH = ROOT / "config" / "projects.json"
LOGS_PATH = ROOT / "scheduler" / "logs" / "expense_processor.log"
PYTHON = sys.executable

PORT = int(os.getenv("DASHBOARD_PORT", "8770"))

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)

# Track in-process runs so the dashboard can show "running..."
_run_lock = threading.Lock()
_run_state = {"running": False, "started": None, "finished": None, "exit_code": None}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list_weeks() -> list[dict]:
    """Return a list of {week_label, has_summary, summary_files} for each report week."""
    if not REPORTS_DIR.exists():
        return []
    weeks = []
    for week_dir in sorted(REPORTS_DIR.iterdir(), reverse=True):
        if not week_dir.is_dir():
            continue
        summaries = sorted(week_dir.glob("summary_*.md"))
        weeks.append(
            {
                "week_label": week_dir.name,
                "has_summary": bool(summaries),
                "contractors": [s.stem.replace("summary_", "") for s in summaries],
                "modified": datetime.fromtimestamp(week_dir.stat().st_mtime).isoformat(timespec="seconds"),
            }
        )
    return weeks


def _read_markdown_as_html(md_path: Path) -> str:
    if not md_path.exists():
        return "<p><em>(no report)</em></p>"
    text = md_path.read_text(encoding="utf-8")
    try:
        import markdown as md
        return md.markdown(text, extensions=["tables", "fenced_code"])
    except ImportError:
        return f"<pre style='white-space: pre-wrap'>{text}</pre>"


def _ledger_summary() -> dict:
    if not LEDGER_PATH.exists():
        return {"entries": 0, "total_extracted_usd": 0.0}
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    total = sum(float(v.get("extracted_total_usd") or 0) for v in ledger.values())
    return {"entries": len(ledger), "total_extracted_usd": round(total, 2)}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    weeks = _list_weeks()
    ledger = _ledger_summary()
    return render_template(
        "index.html",
        weeks=weeks,
        ledger=ledger,
        run_state=_run_state,
        latest_week=weeks[0] if weeks else None,
    )


@app.route("/report/<week_label>")
def report(week_label: str):
    week_dir = REPORTS_DIR / week_label
    if not week_dir.exists():
        abort(404)
    summaries = sorted(week_dir.glob("summary_*.md"))
    if not summaries:
        abort(404)

    pick = request.args.get("contractor")
    if pick:
        target = week_dir / f"summary_{pick}.md"
        if not target.exists():
            abort(404)
        chosen = target
    else:
        chosen = summaries[0]

    contractors_avail = [s.stem.replace("summary_", "") for s in summaries]
    html = _read_markdown_as_html(chosen)
    csv_path = week_dir / chosen.name.replace("summary_", "ledger_").replace(".md", ".csv")
    receipts_dir = week_dir / "receipts" / chosen.stem.replace("summary_", "")
    receipt_files = sorted(receipts_dir.glob("*.pdf")) if receipts_dir.exists() else []

    return render_template(
        "report.html",
        week_label=week_label,
        contractor=chosen.stem.replace("summary_", ""),
        contractors_avail=contractors_avail,
        body_html=html,
        csv_path=csv_path,
        receipt_count=len(receipt_files),
        receipt_files=[f.name for f in receipt_files],
    )


@app.route("/rules")
def rules_page():
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    rules_pretty = json.dumps(rules, indent=2)
    changelog_html = _read_markdown_as_html(CHANGELOG_PATH)
    return render_template(
        "rules.html",
        rules=rules,
        rules_pretty=rules_pretty,
        changelog_html=changelog_html,
    )


@app.route("/contractors")
def contractors_page():
    if not CONTRACTORS_PATH.exists():
        return render_template("contractors.html", contractors=[], error="contractors.json not found.")
    data = json.loads(CONTRACTORS_PATH.read_text(encoding="utf-8"))
    return render_template("contractors.html", contractors=data.get("contractors", []), error=None)


@app.route("/run", methods=["POST"])
def run_now():
    """Spawn the expense_processor as a background subprocess."""
    with _run_lock:
        if _run_state["running"]:
            return jsonify({"ok": False, "error": "A run is already in progress"}), 409
        _run_state.update(
            running=True,
            started=datetime.now().isoformat(timespec="seconds"),
            finished=None,
            exit_code=None,
        )

    def _bg():
        try:
            cp = subprocess.run(
                [PYTHON, str(ROOT / "scheduler" / "expense_processor.py")],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            with _run_lock:
                _run_state.update(
                    running=False,
                    finished=datetime.now().isoformat(timespec="seconds"),
                    exit_code=cp.returncode,
                )
        except Exception as e:
            with _run_lock:
                _run_state.update(
                    running=False,
                    finished=datetime.now().isoformat(timespec="seconds"),
                    exit_code=-1,
                    error=str(e),
                )

    threading.Thread(target=_bg, daemon=True).start()
    return jsonify({"ok": True, "started": _run_state["started"]})


@app.route("/status")
def status():
    return jsonify(_run_state)


@app.route("/log")
def log():
    """Return the tail of scheduler/logs/expense_processor.log."""
    if not LOGS_PATH.exists():
        return jsonify({"lines": []})
    text = LOGS_PATH.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()[-200:]
    return jsonify({"lines": lines})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import webbrowser
    url = f"http://localhost:{PORT}"
    print(f"Spark Expense Engine dashboard starting at {url}")
    # Best-effort: open browser tab. Don't crash if it fails (e.g. headless).
    try:
        webbrowser.open(url)
    except Exception:
        pass
    app.run(host="127.0.0.1", port=PORT, debug=False)


if __name__ == "__main__":
    main()
