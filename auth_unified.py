"""
Unified Google OAuth2 authorization script — Spark Expense Engine.
===================================================================
This project uses a STANDALONE token.json (not shared with the EA).
Run this script ONCE after placing credentials.json in the project root.

Run: python auth_unified.py

If the existing token already has all scopes, this does nothing.
If any scope is missing, it opens a browser for re-authorization.
"""

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path
import json
import shutil
import datetime

# Must match google_auth.py exactly. v1 = drive.readonly only.
ALL_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
]

BASE = Path(__file__).parent
CREDENTIALS = BASE / "credentials.json"
TOKEN = BASE / "token.json"


def check_scopes() -> list[str]:
    """Return list of missing scopes, or empty list if all present."""
    if not TOKEN.exists():
        return ALL_SCOPES
    try:
        data = json.loads(TOKEN.read_text(encoding="utf-8"))
        existing = set(data.get("scopes", []))
        return [s for s in ALL_SCOPES if s not in existing]
    except Exception:
        return ALL_SCOPES


def main():
    missing = check_scopes()
    if not missing:
        print("Token already has all required scopes. No re-auth needed.")
        data = json.loads(TOKEN.read_text(encoding="utf-8"))
        print(f"Scopes: {data.get('scopes', [])}")
        return

    print(f"Missing scopes: {missing}")
    print("Browser will open for re-authorization with ALL scopes...")

    # Back up existing token
    if TOKEN.exists():
        backup = TOKEN.with_suffix(f".backup-{datetime.date.today().isoformat()}")
        shutil.copy2(TOKEN, backup)
        print(f"Backed up existing token to {backup}")

    if not CREDENTIALS.exists():
        print(f"ERROR: credentials.json not found at {CREDENTIALS}")
        print("Download it from Google Cloud Console -> APIs & Credentials -> OAuth 2.0 Client IDs")
        print("Make sure to use a NEW OAuth client (not the EA's tactical-racer-491515-j9 project).")
        return

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), ALL_SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN.write_text(creds.to_json())
    print(f"\nAuthorization complete. Token saved to {TOKEN}")
    print(f"Scopes: {ALL_SCOPES}")


if __name__ == "__main__":
    main()
