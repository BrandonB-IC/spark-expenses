"""
Flag potential duplicate receipts (same receipt uploaded as more than one file).

Per-file SHA dedup only catches byte-identical uploads. A receipt re-downloaded
and re-uploaded, or the same charge filed in two folders, slips through. This
audits the ledger for likely duplicates so they can be voided via adjustments.

Signals (per contractor):
  A. Same extracted amount on 2+ different files  -> strong duplicate suspects.
  B. Same merchant token (from the filename) with amounts within 5%  -> possible.

  python scripts/find_duplicates.py                 # all contractors
  python scripts/find_duplicates.py --contractor dan

Read-only. Prints candidate groups; voiding is a separate, human-confirmed step.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import adjustments_store as adjs

LEDGER_PATH = ROOT / "ledger.json"

STOP = {"spark", "usd", "receipt", "copy", "of", "the", "and", "for", "jun", "jul",
        "may", "apr", "aug", "sep", "oct", "nov", "dec", "jan", "feb", "mar",
        "confirmation", "order", "invoice", "pdf"}


def merchant_tokens(filename: str) -> set[str]:
    stem = re.sub(r"\.[a-z0-9]+$", "", (filename or "").lower())
    words = re.split(r"[^a-z]+", stem)
    return {w for w in words if len(w) >= 4 and w not in STOP}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contractor")
    args = ap.parse_args()

    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    adjustments = adjs.load_adjustments()

    by_contractor = defaultdict(list)
    for sha, e in ledger.items():
        cid = e.get("contractor_id")
        if args.contractor and cid != args.contractor:
            continue
        by_contractor[cid].append({
            "sha": sha,
            "filename": e.get("filename") or "",
            "project": e.get("project_id") or "",
            "amount": round(float(e.get("extracted_total_usd") or 0), 2),
            "voided": adjustments.get(sha, {}).get("type") == "void",
        })

    total_flagged = 0
    for cid, files in sorted(by_contractor.items()):
        groups = []

        # A. Same exact amount.
        by_amount = defaultdict(list)
        for f in files:
            if f["amount"] > 0:
                by_amount[f["amount"]].append(f)
        for amt, fs in by_amount.items():
            if len(fs) >= 2:
                groups.append(("same amount", fs))

        # B. Shared merchant token + amounts within 5%.
        seen_pairs = set()
        for i, a in enumerate(files):
            for b in files[i + 1:]:
                if a["amount"] <= 0 or b["amount"] <= 0:
                    continue
                if a["amount"] == b["amount"]:
                    continue  # already caught by A
                shared = merchant_tokens(a["filename"]) & merchant_tokens(b["filename"])
                hi = max(a["amount"], b["amount"])
                if shared and abs(a["amount"] - b["amount"]) / hi <= 0.05:
                    key = tuple(sorted([a["sha"], b["sha"]]))
                    if key not in seen_pairs:
                        seen_pairs.add(key)
                        groups.append((f"merchant '{'/'.join(sorted(shared))}' ~amount", [a, b]))

        if not groups:
            continue
        print(f"\n=== {cid} - {len(groups)} potential duplicate group(s) ===")
        for reason, fs in groups:
            total_flagged += 1
            print(f"  [{reason}]")
            for f in fs:
                mark = "  (VOIDED)" if f["voided"] else ""
                print(f"     ${f['amount']:>9.2f}  {f['project']:12}  {f['filename'][:48]}{mark}")

    if total_flagged == 0:
        print("No potential duplicates found.")
    else:
        print(f"\n{total_flagged} group(s) to review. Confirm real duplicates, then void the extra "
              f"copy via adjustments (set_void) and rebuild claims.")


if __name__ == "__main__":
    main()
