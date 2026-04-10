"""
Phase 3 test — rules engine + report builder against cached extraction data.

Loads tests/phase2_smoke_test_results.json (the cached output of the vision
extractor) and runs it through rules_engine.classify() + report_builder. This
costs $0 because no API calls are made — we're testing the deterministic
post-processing layer in isolation.

Run: python tests/phase3_rules_test.py

Outputs:
  - tests/phase3_summary.md  (the markdown report)
  - tests/phase3_ledger.csv  (the accounting CSV)
  - prints the markdown to stdout for inspection
"""

import json
import sys
from pathlib import Path

# Force UTF-8 stdout so Windows cp1252 console doesn't choke on any unicode in the report
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.rules_engine import classify
from pipeline.report_builder import build_markdown_summary, build_csv_ledger


def main():
    # Load cached extraction
    extraction_path = ROOT / "tests" / "phase2_smoke_test_results.json"
    if not extraction_path.exists():
        print(f"ERROR: {extraction_path} not found. Run phase2_smoke_test.py first.")
        return 1
    cached = json.loads(extraction_path.read_text(encoding="utf-8"))

    # Flatten cached results into a list of receipts. We carry the drive_path
    # and sha256 onto each receipt so they show up in the CSV ledger.
    flat_receipts = []
    for file_result in cached:
        if "error" in file_result:
            continue
        for rec in file_result.get("extracted", []):
            rec = dict(rec)
            rec["drive_path"] = file_result.get("drive_path")
            rec["sha256"] = file_result.get("sha256")
            # Project ID is encoded in the drive_path: "brandon/<project>/<file>"
            parts = (file_result.get("drive_path") or "").split("/")
            if len(parts) >= 2:
                rec["project_id"] = parts[1]
            flat_receipts.append(rec)

    print(f"Loaded {len(flat_receipts)} extracted receipts from cache.\n")

    # Load rules + contractor profile
    rules = json.loads((ROOT / "config" / "expense-rules.json").read_text(encoding="utf-8"))
    contractors_data = json.loads((ROOT / "config" / "contractors.json").read_text(encoding="utf-8"))
    brandon = next(c for c in contractors_data["contractors"] if c["id"] == "brandon")

    # Run rules
    classified = classify(flat_receipts, rules, brandon)
    classified["rules_version"] = rules.get("version", "unknown")

    # Build outputs
    md = build_markdown_summary(
        classified,
        contractor=brandon,
        project_filter="WHI",
        week_label="2026 San Diego trip",
    )
    csv_text = build_csv_ledger(classified["receipts"], contractor_id="brandon")

    # Write to disk
    md_path = ROOT / "tests" / "phase3_summary.md"
    csv_path = ROOT / "tests" / "phase3_ledger.csv"
    md_path.write_text(md, encoding="utf-8")
    csv_path.write_text(csv_text, encoding="utf-8")

    # Echo the markdown to stdout
    print("=" * 80)
    print("MARKDOWN REPORT")
    print("=" * 80)
    print(md)
    print()
    print("=" * 80)
    print(f"Wrote: {md_path}")
    print(f"Wrote: {csv_path}")
    print()

    # Quick numerical sanity-check vs expectations
    s = classified["summary"]
    print("=" * 80)
    print("SANITY CHECK")
    print("=" * 80)
    expected_extracted = 745.96
    print(
        f"Total extracted:      {s['total_extracted']:>10}  "
        f"(expected ~{expected_extracted})  "
        f"{'OK' if abs(s['total_extracted'] - expected_extracted) < 0.01 else 'MISMATCH'}"
    )
    print(f"Travel days:          {s['travel_days']}")
    print(f"Per-diem added:       {s['total_per_diem_added']:>10}")
    print(f"Replaced by per-diem: {s['total_replaced_by_per_diem']:>10}")
    print(f"Net per-diem impact:  {s['net_per_diem_impact']:>+10}")
    print(f"Total reimbursable:   {s['total_reimbursable']:>10}")
    print(f"Items flagged:        {s['flag_count']} (${s['flagged_amount']})")
    print()

    # Manual recompute as a cross-check
    print("Manual recompute:")
    print(f"  airfare $540.78 + wifi $0 (per-diem) + uber1 $39.74 + uber2 $51.35")
    print(f"  + lyft $76.73 + peets $0 (per-diem) + phils $0 (per-diem)")
    print(f"  + per-diem 2 days @ $100 = $200")
    print(
        f"  = 540.78 + 0 + 39.74 + 51.35 + 76.73 + 0 + 0 + 200 = "
        f"${540.78 + 39.74 + 51.35 + 76.73 + 200:.2f}"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
