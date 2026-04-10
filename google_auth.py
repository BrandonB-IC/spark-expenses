"""
Shared Google OAuth credential loader for the Spark Expense Engine.
====================================================================
All Drive API calls in this project MUST use load_credentials() from this
module instead of calling Credentials.from_authorized_user_file() directly.

Why: when google.oauth2.credentials.Credentials is loaded with a narrow
scope list and then refreshed and saved back, the saved token contains ONLY
those narrow scopes — silently dropping any other scopes that were on disk.
This bug burned the EA project twice (2026-04-09 and 2026-04-10) and is the
reason this helper exists everywhere we touch Google APIs.

Fix: this loader always passes the FULL scope list, so refresh+save preserves
all scopes. Scope enforcement still happens server-side per API call —
loading "extra" scopes is harmless.

NOTE: This is a STANDALONE token (not shared with the EA). v1 uses readonly
Drive scope only — receipts stay in place; ledger.json tracks processing
state. Brandon's standing rule: never delete/modify Google Drive files.
"""

from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# v1: drive.readonly only. If we ever need to move/modify files, expand here
# AND update auth_unified.py simultaneously, then re-run auth_unified.py.
ALL_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
]

BASE = Path(__file__).parent
TOKEN_PATH = BASE / "token.json"


def load_credentials() -> Credentials:
    """Load Google credentials with ALL scopes. Refreshes and saves if expired."""
    if not TOKEN_PATH.exists():
        raise FileNotFoundError(
            f"token.json not found at {TOKEN_PATH}. Run: python auth_unified.py"
        )

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), ALL_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    return creds
