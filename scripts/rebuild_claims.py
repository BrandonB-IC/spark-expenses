"""
Rebuild reimbursement claim amounts receipts-only (no per-diem) + adjustments.

Recomputes each selected claim's reimbursable_usd as the sum of its receipts'
adjusted amounts (ledger extracted total, with any override/void from
adjustments.json applied). Preserves claim ids, weeks, and paid status.

Invoice-derived claims (whose receipts are invoice files, e.g. attested invoice
lines) are left untouched — their reimbursable is not a simple ledger sum.

  python scripts/rebuild_claims.py --contractor brandon
  python scripts/rebuild_claims.py --all

Backs up reimbursements.json next to itself before writing.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import adjustments_store as adjs
import pending_invoices_store as pend

LEDGER_PATH = ROOT / "ledger.json"
REIMB_PATH = ROOT / "reimbursements.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contractor", help="Only rebuild this contractor's claims")
    ap.add_argument("--all", action="store_true", help="Rebuild all contractors' claims")
    args = ap.parse_args()
    if not args.contractor and not args.all:
        ap.error("pass --contractor <id> or --all")

    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    data = json.loads(REIMB_PATH.read_text(encoding="utf-8"))
    claims = data.get("claims", [])
    adjustments = adjs.load_adjustments()
    invoice_shas = {l.get("invoice_sha256") for l in pend.load_pending() if l.get("invoice_sha256")}

    # Back up before writing.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = REIMB_PATH.with_name(f"reimbursements.backup-{stamp}.json")
    shutil.copy2(REIMB_PATH, backup)
    print(f"Backed up -> {backup.name}")

    changed = 0
    for c in claims:
        if args.contractor and c.get("contractor_id") != args.contractor:
            continue
        shas = c.get("receipt_shas") or []
        # Skip invoice-derived claims (reimbursable != simple ledger sum).
        if shas and all(s in invoice_shas for s in shas):
            print(f"  SKIP (invoice-derived): {c['id']}  ${c.get('reimbursable_usd')}")
            continue

        new_total = 0.0
        n = 0
        for s in shas:
            base = float((ledger.get(s) or {}).get("extracted_total_usd") or 0)
            amt = adjs.adjusted_amount(adjustments, s, base)
            new_total += amt
            if amt > 0:
                n += 1
        new_total = round(new_total, 2)
        old = float(c.get("reimbursable_usd") or 0)
        if abs(new_total - old) > 0.005 or c.get("n_receipts") != n:
            print(f"  {c['id']:20} ${old:>9.2f} -> ${new_total:>9.2f}  ({c.get('n_receipts')}->{n} receipts)")
            c["reimbursable_usd"] = new_total
            c["n_receipts"] = n
            changed += 1
        else:
            print(f"  {c['id']:20} ${old:>9.2f} (unchanged)")

    data["claims"] = claims
    REIMB_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\nRebuilt {changed} claim(s). Saved reimbursements.json.")


if __name__ == "__main__":
    main()
