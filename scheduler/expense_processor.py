"""
Spark Expense Engine — main orchestrator.

End-to-end pipeline:
    Drive -> dedup against ledger -> vision -> rules -> report -> email -> ledger update

Run modes:
    python scheduler/expense_processor.py                     # all active contractors, current week label
    python scheduler/expense_processor.py --contractor brandon
    python scheduler/expense_processor.py --week 2026-W15
    python scheduler/expense_processor.py --dry-run           # no ledger writes, no email
    python scheduler/expense_processor.py --no-email          # writes everything but skips email
    python scheduler/expense_processor.py --interactive       # extra-verbose for skill use

Outputs (under reports/<week_label>/):
    summary.md          - Markdown report (also emailed)
    ledger.csv          - Accounting CSV
    receipts/           - Original PDFs copied from Drive (audit packet folder)
    run.log             - Per-run log

Ledger:
    ledger.json (project root) — keyed by SHA-256, never deletes entries.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import shutil
import smtplib
import sys
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path

# Make project root importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import os

from pipeline.drive_reader import list_receipts_for_contractor, download_file_bytes
from pipeline.hasher import sha256_bytes
from pipeline.vision_extractor import extract
from pipeline.rules_engine import classify
from pipeline.report_builder import build_markdown_summary, build_csv_ledger


# ---------------------------------------------------------------------------
# Paths + constants
# ---------------------------------------------------------------------------

CONTRACTORS_PATH = ROOT / "config" / "contractors.json"
RULES_PATH = ROOT / "config" / "expense-rules.json"
PROJECTS_PATH = ROOT / "config" / "projects.json"
LEDGER_PATH = ROOT / "ledger.json"
REPORTS_DIR = ROOT / "reports"
LOGS_DIR = ROOT / "scheduler" / "logs"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(week_label: str, verbose: bool) -> logging.Logger:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / "expense_processor.log"
    week_log = REPORTS_DIR / week_label / "run.log"
    week_log.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("expense_processor")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    week_fh = logging.FileHandler(week_log, encoding="utf-8")
    week_fh.setFormatter(fmt)
    logger.addHandler(week_fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

def load_ledger() -> dict:
    if not LEDGER_PATH.exists():
        return {}
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def save_ledger(ledger: dict) -> None:
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")


# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------

def load_contractors() -> list[dict]:
    if not CONTRACTORS_PATH.exists():
        raise FileNotFoundError(
            f"contractors.json not found at {CONTRACTORS_PATH}. "
            f"Copy contractors.json.template and fill in real values."
        )
    return json.loads(CONTRACTORS_PATH.read_text(encoding="utf-8"))["contractors"]


def load_rules() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def load_projects() -> dict:
    return json.loads(PROJECTS_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Per-contractor processing
# ---------------------------------------------------------------------------

def process_contractor(
    contractor: dict,
    rules: dict,
    ledger: dict,
    logger: logging.Logger,
    week_dir: Path,
    dry_run: bool,
) -> dict:
    """Process one contractor's receipts. Returns the classified result.

    Receipts already in the ledger are skipped (deduplication by SHA-256).
    Newly-processed receipts are added to the ledger only if not dry_run.
    """
    cid = contractor["id"]
    logger.info(f"=== Processing contractor: {contractor.get('display_name', cid)} ===")

    folder_id = contractor.get("drive_folder_id")
    if not folder_id:
        logger.warning(f"  No drive_folder_id set for {cid}; skipping.")
        return None

    drive_files = list_receipts_for_contractor(cid, folder_id)
    logger.info(f"  Found {len(drive_files)} files in Drive.")

    receipts_dir = week_dir / "receipts" / cid
    receipts_dir.mkdir(parents=True, exist_ok=True)

    flat_receipts: list[dict] = []
    new_ledger_entries = 0
    skipped_already_in_ledger = 0
    extraction_cost_input_tokens = 0
    extraction_cost_output_tokens = 0

    for f in drive_files:
        try:
            file_bytes = download_file_bytes(f.file_id)
            sha = sha256_bytes(file_bytes)

            if sha in ledger:
                skipped_already_in_ledger += 1
                logger.debug(f"  SKIP (already in ledger): {f.name}")
                continue

            logger.info(f"  EXTRACT: {f.name}  ({len(file_bytes):,} bytes)")
            extracted, meta = extract(file_bytes, f.mime_type, filename=f.name)

            extraction_cost_input_tokens += meta["input_tokens"]
            extraction_cost_output_tokens += meta["output_tokens"]

            for rec in extracted:
                rec = dict(rec)
                rec["contractor_id"] = cid
                rec["project_id"] = f.project_id
                rec["drive_path"] = f.drive_path
                rec["sha256"] = sha
                flat_receipts.append(rec)

            # Save the original PDF into the per-week receipts folder for audit
            receipt_path = receipts_dir / f.name
            receipt_path.write_bytes(file_bytes)

            # Add to ledger
            if not dry_run:
                ledger[sha] = {
                    "filename": f.name,
                    "drive_path": f.drive_path,
                    "drive_file_id": f.file_id,
                    "contractor_id": cid,
                    "project_id": f.project_id,
                    "processed_date": dt.datetime.now().isoformat(timespec="seconds"),
                    "extracted_count": len(extracted),
                    "extracted_total_usd": round(
                        sum(float(r.get("amount") or 0) for r in extracted), 2
                    ),
                    "model": meta["model"],
                    "input_tokens": meta["input_tokens"],
                    "output_tokens": meta["output_tokens"],
                    "dedup_dropped": meta.get("dedup_dropped", 0),
                }
                new_ledger_entries += 1

        except Exception as e:
            logger.error(f"  FAILED on {f.name}: {e}")
            logger.debug(traceback.format_exc())

    logger.info(
        f"  Summary: {len(flat_receipts)} new receipts extracted, "
        f"{skipped_already_in_ledger} skipped (already in ledger), "
        f"{new_ledger_entries} new ledger entries"
    )

    # Apply rules
    classified = classify(flat_receipts, rules, contractor)
    classified["rules_version"] = rules.get("version", "unknown")
    classified["extraction_cost"] = {
        "input_tokens": extraction_cost_input_tokens,
        "output_tokens": extraction_cost_output_tokens,
        # Haiku 4.5: $0.80/M input, $4/M output
        "approx_usd": round(
            extraction_cost_input_tokens / 1_000_000 * 0.80
            + extraction_cost_output_tokens / 1_000_000 * 4.00,
            4,
        ),
    }
    classified["counts"] = {
        "files_in_drive": len(drive_files),
        "skipped_already_in_ledger": skipped_already_in_ledger,
        "new_ledger_entries": new_ledger_entries,
        "extracted_receipts": len(flat_receipts),
    }
    return classified


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def send_report_email(
    subject: str,
    html_body: str,
    attachments: list[Path],
    logger: logging.Logger,
) -> None:
    sender = os.getenv("GMAIL_SENDER", "brandon@improvement-science.com")
    password = os.getenv("GMAIL_APP_PASSWORD")
    recipient = os.getenv("REPORT_RECIPIENT", sender)
    cc_raw = os.getenv("REPORT_CC", "").strip()
    cc_list = [a.strip() for a in cc_raw.split(",") if a.strip()]

    if not password:
        logger.error("GMAIL_APP_PASSWORD not set in .env; cannot send email.")
        return

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)

    msg.attach(MIMEText(html_body, "html"))

    for path in attachments:
        if not path.exists():
            continue
        with open(path, "rb") as fh:
            part = MIMEApplication(fh.read(), Name=path.name)
        part["Content-Disposition"] = f'attachment; filename="{path.name}"'
        msg.attach(part)

    recipients = [recipient] + cc_list
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())

    logger.info(f"Email sent to {recipient}" + (f" (cc: {', '.join(cc_list)})" if cc_list else ""))


# ---------------------------------------------------------------------------
# Markdown -> HTML for email body
# ---------------------------------------------------------------------------

def markdown_to_html_email(md_text: str) -> str:
    """Convert markdown to a self-contained HTML email body."""
    try:
        import markdown as md
        body_html = md.markdown(md_text, extensions=["tables", "fenced_code"])
    except ImportError:
        # Fallback: wrap in <pre> if the package is missing
        body_html = f"<pre style='font-family: monospace; white-space: pre-wrap'>{md_text}</pre>"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 800px; margin: 20px auto; padding: 0 20px; color: #222; }}
  h1 {{ color: #1a4d8f; border-bottom: 2px solid #1a4d8f; padding-bottom: 8px; }}
  h2 {{ color: #2e6cb5; margin-top: 30px; }}
  h3 {{ color: #444; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 10px; text-align: left; vertical-align: top; font-size: 13px; }}
  th {{ background: #f0f4fa; font-weight: 600; }}
  tr:nth-child(even) {{ background: #fafbfd; }}
  code {{ background: #f4f4f4; padding: 1px 5px; border-radius: 3px; font-size: 12px; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 30px 0 15px; }}
</style>
</head>
<body>
{body_html}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Top-level run
# ---------------------------------------------------------------------------

def current_week_label() -> str:
    today = dt.date.today()
    iso_year, iso_week, _ = today.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def run(
    contractor_filter: str | None,
    week_label: str | None,
    dry_run: bool,
    no_email: bool,
    interactive: bool,
) -> int:
    week_label = week_label or current_week_label()
    week_dir = REPORTS_DIR / week_label
    week_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(week_label, verbose=interactive)
    logger.info(f"=== Spark Expense Engine run started ({week_label}) ===")
    if dry_run:
        logger.info("DRY RUN: ledger will not be updated, email will not be sent.")

    rules = load_rules()
    contractors = load_contractors()
    if contractor_filter:
        contractors = [c for c in contractors if c["id"] == contractor_filter]
        if not contractors:
            logger.error(f"No contractor matches id '{contractor_filter}'")
            return 1

    ledger = load_ledger()
    logger.info(f"Loaded ledger with {len(ledger)} existing entries.")

    all_classified = []
    for c in contractors:
        if not c.get("active", True):
            logger.info(f"Skipping inactive contractor: {c['id']}")
            continue
        result = process_contractor(c, rules, ledger, logger, week_dir, dry_run)
        if result is not None:
            all_classified.append((c, result))

    if not dry_run:
        save_ledger(ledger)
        logger.info(f"Ledger saved ({len(ledger)} total entries).")

    # Build per-contractor reports
    md_files = []
    csv_files = []
    for c, classified in all_classified:
        cid = c["id"]
        md = build_markdown_summary(
            classified,
            contractor=c,
            week_label=week_label,
        )
        csv_text = build_csv_ledger(classified["receipts"], contractor_id=cid)

        md_path = week_dir / f"summary_{cid}.md"
        csv_path = week_dir / f"ledger_{cid}.csv"
        md_path.write_text(md, encoding="utf-8")
        csv_path.write_text(csv_text, encoding="utf-8")
        md_files.append(md_path)
        csv_files.append(csv_path)
        logger.info(f"Wrote {md_path.name} and {csv_path.name}")

    # Determine if there's anything new to email about
    total_new = sum(c[1]["counts"]["extracted_receipts"] for c in all_classified)
    if total_new == 0:
        logger.info("No new receipts to report on this run. Skipping email.")
        logger.info("=== Run complete ===")
        return 0

    # Combined email body
    email_body_md_parts = []
    for c, classified in all_classified:
        if classified["counts"]["extracted_receipts"] == 0:
            continue
        md = build_markdown_summary(classified, contractor=c, week_label=week_label)
        email_body_md_parts.append(md)
        cost = classified["extraction_cost"]
        email_body_md_parts.append(
            f"\n_API cost for {c['display_name']}: "
            f"~${cost['approx_usd']:.4f} ({cost['input_tokens']} in / {cost['output_tokens']} out tokens)_\n"
        )

    combined_md = "\n\n---\n\n".join(email_body_md_parts)
    html_body = markdown_to_html_email(combined_md)

    if no_email or dry_run:
        logger.info(f"Email send skipped ({'dry-run' if dry_run else '--no-email'}).")
    else:
        try:
            send_report_email(
                subject=f"Spark Expense Report — {week_label}",
                html_body=html_body,
                attachments=csv_files,
                logger=logger,
            )
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            logger.debug(traceback.format_exc())

    logger.info("=== Run complete ===")
    return 0


def main():
    p = argparse.ArgumentParser(description="Spark Expense Engine — process contractor receipts")
    p.add_argument("--contractor", help="Filter by contractor id (default: all active)")
    p.add_argument("--week", help="Week label (default: current ISO week, e.g. 2026-W15)")
    p.add_argument("--dry-run", action="store_true", help="Don't update ledger, don't send email")
    p.add_argument("--no-email", action="store_true", help="Update ledger but skip email")
    p.add_argument("--interactive", action="store_true", help="Verbose logging for /process-expenses skill")
    args = p.parse_args()

    code = run(
        contractor_filter=args.contractor,
        week_label=args.week,
        dry_run=args.dry_run,
        no_email=args.no_email,
        interactive=args.interactive,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
