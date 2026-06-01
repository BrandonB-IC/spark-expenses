"""
Spark Expense Engine — Drive auth health check.
================================================
Runs a trivial Google Drive API call to verify the OAuth token is alive.
If it fails (e.g., the refresh token was revoked/expired — common when the
OAuth consent screen is still in "Testing" publishing status, which expires
refresh tokens after 7 days), email Brandon so a dead token surfaces instead
of the weekly run failing silently.

Email sending uses SMTP + GMAIL_APP_PASSWORD (see send_report_email), which is
INDEPENDENT of the Drive OAuth token — so the alert still sends even when Drive
auth is dead.

Run:    python -m scheduler.health_check
Exit:   0 = healthy, 1 = unhealthy (alert email attempted)
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from googleapiclient.discovery import build

from google_auth import load_credentials
from scheduler.expense_processor import send_report_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("health_check")


def check_drive() -> tuple[bool, str]:
    """Return (ok, detail). A trivial files.list() forces a token refresh."""
    try:
        creds = load_credentials()
        svc = build("drive", "v3", credentials=creds)
        svc.files().list(
            pageSize=1,
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        return True, "Drive auth OK"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    ok, detail = check_drive()
    if ok:
        logger.info(detail)
        return 0

    logger.error(f"HEALTH CHECK FAILED: {detail}")
    today = dt.date.today().isoformat()
    html = f"""<html><body style="font-family:-apple-system,Segoe UI,sans-serif;color:#222">
    <h2 style="color:#b00020">Spark Expense Engine: Drive auth FAILED</h2>
    <p>The daily health check on <b>{today}</b> could not reach Google Drive, so
    the next weekly expense run will process <b>nothing</b> until this is fixed.</p>
    <p><b>Error:</b> <code>{detail}</code></p>
    <p>Most likely cause: the OAuth consent screen for the "Spark Expense Engine"
    Google Cloud project is still in <b>Testing</b> publishing status, which
    expires refresh tokens after 7 days.</p>
    <p><b>To fix (have Claude do it):</b></p>
    <ol>
      <li>Move <code>token.json</code> aside, run <code>python auth_unified.py</code>,
          authorize as <b>improvement.science@gmail.com</b>.</li>
      <li>In the Google Cloud Console for that project, publish the OAuth consent
          screen to <b>In production</b> so refresh tokens stop expiring.</li>
    </ol>
    </body></html>"""
    try:
        send_report_email(
            subject="[ACTION NEEDED] Spark Expense Engine — Drive auth failed",
            html_body=html,
            attachments=[],
            logger=logger,
        )
        logger.info("Alert email sent.")
    except Exception as e:
        logger.error(f"Could not send alert email: {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
