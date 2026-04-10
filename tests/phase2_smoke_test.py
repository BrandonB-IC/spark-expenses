"""
Phase 2 smoke test — end-to-end vision extraction on real receipts.

Lists every receipt in Brandon's Drive folder, downloads each, runs Claude
vision extraction, and prints a side-by-side summary so we can spot-check
accuracy. Also tallies token usage for cost honesty.

Run: python tests/phase2_smoke_test.py
"""

import json
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path so `pipeline.*` and `google_auth` import
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from pipeline.drive_reader import list_receipts_for_contractor, download_file_bytes
from pipeline.hasher import sha256_bytes
from pipeline.vision_extractor import extract


# Brandon's contractor folder (from config/contractors.json)
CONTRACTOR_ID = "brandon"
BRANDON_FOLDER_ID = "1MEtRQNDL7lZj0hyldHQMaGguxb_pDxTP"


def fmt_money(v):
    if v is None:
        return "    -   "
    try:
        return f"${float(v):>8,.2f}"
    except (TypeError, ValueError):
        return f"  {v!s:>8}"


def main():
    print("=" * 80)
    print("PHASE 2 SMOKE TEST — Spark Expense Engine")
    print("=" * 80)

    print("\n[1/3] Listing receipts in Brandon's Drive folder...")
    receipts = list_receipts_for_contractor(CONTRACTOR_ID, BRANDON_FOLDER_ID)
    print(f"      Found {len(receipts)} files.")
    for r in receipts:
        size_kb = (r.size_bytes or 0) / 1024
        print(f"        - [{r.project_id}] {r.name}  ({size_kb:.0f} KB)")

    print("\n[2/3] Downloading + extracting each receipt...")
    print("      (this calls Claude vision — costs ~$0.003-0.01 per file with Haiku)\n")

    total_input_tokens = 0
    total_output_tokens = 0
    total_extracted_receipts = 0
    all_results = []

    for i, r in enumerate(receipts, 1):
        print(f"  [{i}/{len(receipts)}] {r.name}")
        t0 = time.time()
        try:
            file_bytes = download_file_bytes(r.file_id)
            sha = sha256_bytes(file_bytes)
            print(f"        sha256: {sha[:16]}...  ({len(file_bytes):,} bytes)")

            extracted, meta = extract(file_bytes, r.mime_type, filename=r.name)
            elapsed = time.time() - t0

            total_input_tokens += meta["input_tokens"]
            total_output_tokens += meta["output_tokens"]
            total_extracted_receipts += len(extracted)

            print(
                f"        extracted: {len(extracted)} receipt(s)  "
                f"({meta['input_tokens']} in / {meta['output_tokens']} out tokens, "
                f"{elapsed:.1f}s)"
            )

            all_results.append({
                "drive_file": r.name,
                "drive_path": r.drive_path,
                "sha256": sha,
                "model": meta["model"],
                "input_tokens": meta["input_tokens"],
                "output_tokens": meta["output_tokens"],
                "extracted": extracted,
            })
        except Exception as e:
            print(f"        ERROR: {e}")
            all_results.append({
                "drive_file": r.name,
                "drive_path": r.drive_path,
                "error": str(e),
            })
        print()

    print("\n[3/3] Summary")
    print("-" * 80)
    print(f"{'#':<3} {'Date':<11} {'Merchant':<30} {'Cat':<18} {'Amount':>10}  Notes")
    print("-" * 80)

    n = 0
    grand_total = 0.0
    for result in all_results:
        if "error" in result:
            n += 1
            print(f"{n:<3} ERROR on {result['drive_file']}: {result['error']}")
            continue
        for rec in result["extracted"]:
            n += 1
            date = (rec.get("date") or "?")[:10]
            merchant = (rec.get("merchant") or "?")[:30]
            cat = (rec.get("category") or "?")[:18]
            amt = rec.get("amount")
            notes = rec.get("notes") or ""
            print(
                f"{n:<3} {date:<11} {merchant:<30} {cat:<18} {fmt_money(amt)}  {notes}"
            )
            try:
                grand_total += float(amt) if amt is not None else 0.0
            except (TypeError, ValueError):
                pass
    print("-" * 80)
    print(f"{'GRAND TOTAL':>62} {fmt_money(grand_total)}")
    print()

    # Cost estimate
    # Haiku 4.5 pricing as of 2026-04: $0.80/M input, $4/M output
    in_cost = total_input_tokens / 1_000_000 * 0.80
    out_cost = total_output_tokens / 1_000_000 * 4.00
    total_cost = in_cost + out_cost
    print(
        f"Token usage: {total_input_tokens:,} input + {total_output_tokens:,} output  "
        f"-> ~${total_cost:.4f} total ({len(receipts)} files, "
        f"{total_extracted_receipts} extracted receipts)"
    )

    # Save full results to a JSON file for inspection
    out_path = ROOT / "tests" / "phase2_smoke_test_results.json"
    out_path.write_text(json.dumps(all_results, indent=2, default=str), encoding="utf-8")
    print(f"\nFull results written to: {out_path}")


if __name__ == "__main__":
    main()
