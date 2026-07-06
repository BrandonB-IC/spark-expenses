"""
Compliance rules engine for the Spark Expense Engine.

PURE FUNCTIONS — no I/O. Takes extracted receipt dicts + a contractor profile
+ a rules dict and returns a classified result. The orchestrator
(scheduler/expense_processor.py) is responsible for loading the inputs and
writing the outputs.

Design notes:
- Travel days are inferred from non-meal travel categories (rideshare, hotel,
  travel-other). We do NOT use the airfare receipt date because that's often
  the booking date, not the actual trip date. If you only have an airfare
  receipt and nothing else, the engine won't detect any travel days — that
  edge case is intentional for v1 and will need a v2 fix (parse itinerary
  dates from notes, or accept manual day-count input).
- Per-diem replaces meals AND incidentals (e.g., in-flight wifi) on travel
  days. The list of incidentals is configurable in expense-rules.json.
- Flagging never blocks reimbursement — it just adds a `flagged: true` and a
  `flag_reasons: [...]` to the receipt so the auditor sees it on review.
- Synthetic per-diem rows have `per_diem_synthetic: true` so they can be
  distinguished from real receipts in the report.
"""

from __future__ import annotations

from datetime import date as Date
from typing import Iterable

# ---------------------------------------------------------------------------
# Category constants
# ---------------------------------------------------------------------------

TRAVEL_DAY_TRIGGER_CATEGORIES = {
    "travel-rideshare",
    "travel-hotel",
    "travel-other",
}

MEAL_CATEGORIES = {"meals"}


# ---------------------------------------------------------------------------
# Travel day detection
# ---------------------------------------------------------------------------

def detect_travel_days(receipts: Iterable[dict]) -> set[str]:
    """Return the set of YYYY-MM-DD strings on which travel was detected.

    A day is a travel day if any receipt on that day belongs to a
    TRAVEL_DAY_TRIGGER_CATEGORIES (rideshare/hotel/other). Airfare booking
    receipts are intentionally excluded because the receipt date is usually
    the booking date, not the trip date.
    """
    travel_days: set[str] = set()
    for r in receipts:
        if r.get("category") in TRAVEL_DAY_TRIGGER_CATEGORIES and r.get("date"):
            travel_days.add(r["date"])
    return travel_days


# ---------------------------------------------------------------------------
# Per-diem application
# ---------------------------------------------------------------------------

def _is_incidental(receipt: dict, incidentals_includes: list[str]) -> bool:
    """Return True if this receipt counts as an 'incidental' that per-diem replaces."""
    cat = receipt.get("category") or ""
    merchant = (receipt.get("merchant") or "").lower()
    line_items = receipt.get("line_items") or []

    # Check by category first
    if cat == "incidentals":
        return True

    # In-flight wifi: looks like travel-airfare but is wifi-only.
    # Heuristic: small amount (<$30) AND merchant is an airline AND line items
    # mention wifi/internet, OR notes mention wifi.
    if "in_flight_wifi" in incidentals_includes:
        airline_merchants = {"united airlines", "american airlines", "delta", "southwest", "alaska airlines", "jetblue"}
        is_airline = any(m in merchant for m in airline_merchants)
        wifi_signal = (
            any("wifi" in (li.get("description") or "").lower() for li in line_items)
            or "wifi" in (receipt.get("notes") or "").lower()
            or "wi-fi" in (receipt.get("notes") or "").lower()
        )
        if is_airline and wifi_signal and (receipt.get("amount") or 0) < 30:
            return True

    return False


def apply_per_diem(
    receipts: list[dict],
    travel_days: set[str],
    rules: dict,
) -> tuple[list[dict], list[dict], float]:
    """Apply per-diem replacement to a list of receipts.

    Returns:
        (updated_receipts, synthetic_per_diem_rows, total_per_diem_replaced_amount)

    - updated_receipts: original receipts with `replaced_by_per_diem` flag set
      and `reimbursable_amount` zeroed for replaced items
    - synthetic_per_diem_rows: one synthetic row per travel day, $rate each
    - total_per_diem_replaced_amount: sum of receipt amounts that were zeroed
    """
    per_diem_rules = rules.get("per_diem", {})

    # Per-diem can be switched off entirely (direct receipt reimbursement only).
    # When off: no synthetic per-diem rows, no meal/incidental replacement —
    # each receipt is reimbursed at its own amount (honoring any override).
    if not per_diem_rules.get("enabled", True):
        updated = []
        for r in receipts:
            r = dict(r)
            override = r.get("reimbursable_override")
            r["reimbursable_amount"] = float(override) if override is not None else float(r.get("amount") or 0)
            r["replaced_by_per_diem"] = False
            updated.append(r)
        return updated, [], 0.0

    rate = per_diem_rules.get("rate_usd", 0)
    replaces = set(per_diem_rules.get("replaces", []))  # e.g. {"meals", "incidentals"}
    incidentals_includes = per_diem_rules.get("incidentals_includes", [])

    updated = []
    total_replaced = 0.0

    for r in receipts:
        r = dict(r)  # don't mutate caller's data

        # A reconciled receipt (one that substantiates a held invoice line) carries
        # an explicit reimbursable_override — the invoice's allocated amount. Honor
        # it verbatim and never let per-diem replace it.
        override = r.get("reimbursable_override")
        if override is not None:
            r["replaced_by_per_diem"] = False
            r["reimbursable_amount"] = float(override)
            updated.append(r)
            continue

        is_meal = ("meals" in replaces) and (r.get("category") in MEAL_CATEGORIES)
        is_incidental = ("incidentals" in replaces) and _is_incidental(r, incidentals_includes)

        if (is_meal or is_incidental) and r.get("date") in travel_days:
            r["replaced_by_per_diem"] = True
            r["reimbursable_amount"] = 0.0
            r["per_diem_replacement_reason"] = (
                "meal on travel day — per-diem applies"
                if is_meal else
                "incidental on travel day — per-diem applies (e.g., in-flight wifi)"
            )
            total_replaced += float(r.get("amount") or 0)
        else:
            r["replaced_by_per_diem"] = False
            r["reimbursable_amount"] = float(r.get("amount") or 0)
        updated.append(r)

    # Generate synthetic per-diem rows — one per travel day
    synthetic = []
    for day in sorted(travel_days):
        synthetic.append({
            "date": day,
            "merchant": "(per-diem)",
            "category": "per-diem",
            "currency": "USD",
            "amount": rate,
            "reimbursable_amount": rate,
            "itemization_status": "synthetic",
            "line_items": [],
            "notes": f"Auto-generated per-diem for travel day {day} (replaces meals + incidentals at ${rate}/day)",
            "per_diem_synthetic": True,
            "flagged": False,
            "flag_reasons": [],
            "replaced_by_per_diem": False,
        })

    return updated, synthetic, total_replaced


# ---------------------------------------------------------------------------
# Flagging
# ---------------------------------------------------------------------------

def _great_circle_miles(lat1, lon1, lat2, lon2) -> float:
    """Haversine distance in statute miles."""
    from math import radians, sin, cos, asin, sqrt
    R = 3958.7613
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * R * asin(sqrt(a))


def flag_violations(
    receipts: list[dict],
    rules: dict,
    contractor: dict,
) -> list[dict]:
    """Add `flagged` + `flag_reasons` to each receipt according to the rules.

    Mutates a copy of each receipt and returns the new list. Existing
    `flagged`/`flag_reasons` are preserved (additive).
    """
    out = []
    large_threshold = (rules.get("large_expense") or {}).get("threshold_usd", 10**9)
    hotel_cap = (rules.get("hotel") or {}).get("cap_per_night_usd", 10**9)
    airfare_rules = rules.get("airfare") or {}

    for r in receipts:
        r = dict(r)
        reasons = list(r.get("flag_reasons") or [])
        flagged = bool(r.get("flagged", False))

        amount = r.get("amount") or 0

        # Rule 1: large expense threshold (any single receipt > threshold)
        if amount and amount > large_threshold:
            flagged = True
            reasons.append(f"Large expense: ${amount:.2f} exceeds ${large_threshold} threshold — needs manual review")

        # Rule 2: credit card slip without itemization
        if r.get("itemization_status") == "slip_only":
            flagged = True
            reasons.append("Credit card slip with no itemization — cannot audit line items")

        # Rule 3: hotel — confirm business nights, and check the per-night cap.
        if r.get("category") == "travel-hotel":
            flagged = True
            reasons.append(
                "Hotel — confirm Spark pays only the business nights; exclude any personal/extra "
                "nights (set a per-receipt adjustment if the folio spans more nights than the trip)"
            )
            # naive check: if total > nights * cap, flag. We don't always know
            # nights, so for v1 just compare total to cap (conservative — over-flags).
            if amount > hotel_cap:
                reasons.append(
                    f"Hotel ${amount:.2f} exceeds cap ${hotel_cap}/night — verify number of nights and per-night rate"
                )

        # Rule 4: airfare tier check (skipped if home airport not configured)
        if r.get("category") == "travel-airfare":
            home = (contractor.get("home_airport") or {})
            if home.get("code") in (None, "", "XXX"):
                flagged = True
                reasons.append(
                    "Airfare receipt: contractor home airport not configured — cannot apply distance-based tier cap. Set home_airport in contractors.json."
                )
            else:
                # We don't have the destination airport extracted reliably yet — defer
                # to v2. For now, just enforce the long-haul absolute cap.
                long_haul_cap = (airfare_rules.get("tier_long_haul") or {}).get("cap_usd")
                if long_haul_cap and amount > long_haul_cap:
                    flagged = True
                    reasons.append(
                        f"Airfare ${amount:.2f} exceeds long-haul cap ${long_haul_cap} — needs manual review"
                    )

        # Rule 5: unknown project — handled upstream in drive_reader (project_id
        # comes from folder name); rules engine could check it against projects.json
        # but that's a separate concern.

        r["flagged"] = flagged
        r["flag_reasons"] = reasons
        out.append(r)

    return out


# ---------------------------------------------------------------------------
# Invoice substantiation (Phase B)
# ---------------------------------------------------------------------------

def apply_substantiation(invoice_rows: list[dict], rules: dict) -> list[dict]:
    """Decide, per invoice line, whether it is reimbursable on attestation or
    held pending a receipt (hybrid substantiation policy).

    An invoice line is REIMBURSABLE on attestation only if the policy accepts
    attestation AND the line is neither in a receipt-required category (lodging,
    airfare) nor at/over the per-item receipt threshold. Everything else is HELD
    (reimbursable zeroed, flagged) until the underlying receipt is provided.

    Each row gets a `substantiation_status` of "invoice_attested" or
    "receipt_required". The stated `amount` is always preserved.
    """
    sub = rules.get("substantiation", {})
    attestation_ok = bool(sub.get("invoice_attestation_accepted", False))
    rr_categories = set(sub.get("receipt_required_categories", []))
    rr_threshold = sub.get("receipt_required_over_usd")

    out = []
    for r in invoice_rows:
        r = dict(r)
        r["replaced_by_per_diem"] = False
        amount = float(r.get("amount") or 0)
        cat = r.get("category") or ""
        reasons = list(r.get("flag_reasons") or [])

        triggers = []
        if not attestation_ok:
            triggers.append("receipts-only policy (invoice attestation disabled)")
        if cat in rr_categories:
            triggers.append(f"{cat} always requires a receipt")
        if rr_threshold is not None and amount >= float(rr_threshold):
            triggers.append(f"${amount:,.2f} is at/over the ${rr_threshold} receipt threshold")

        if triggers:
            r["substantiation_status"] = "receipt_required"
            r["reimbursable_amount"] = 0.0
            r["flagged"] = True
            reasons.append("Receipt required before payment — " + "; ".join(triggers))
        else:
            r["substantiation_status"] = "invoice_attested"
            r["reimbursable_amount"] = amount
            r["flagged"] = bool(r.get("flagged", False))
            att_note = "Reimbursed on invoice attestation (under threshold, non-lodging/airfare; no receipt)"
            existing = r.get("notes")
            r["notes"] = f"{existing} · {att_note}" if existing else att_note

        r["flag_reasons"] = reasons
        out.append(r)
    return out


def _is_invoice(row: dict) -> bool:
    return (row.get("doc_type") or "receipt").strip().lower() == "invoice"


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def classify(
    receipts: list[dict],
    rules: dict,
    contractor: dict,
) -> dict:
    """Run the full rules pipeline against a list of extracted rows.

    Invoice-derived rows are separated out and quarantined (Phase A): they never
    drive travel-day detection or per-diem, and never contribute to the
    reimbursable total. Receipt rows flow through the normal pipeline.

    Returns a dict:
        {
            "receipts": [...],          # all rows: receipts + synthetic per-diem + invoices
            "summary": {...},           # totals + flag counts + pending-verification totals
            "warnings": [...],          # things to surface to the user
        }
    """
    receipt_rows = [r for r in receipts if not _is_invoice(r)]
    invoice_rows = [r for r in receipts if _is_invoice(r)]

    travel_days = detect_travel_days(receipt_rows)

    receipts_after_per_diem, synthetic, total_replaced = apply_per_diem(
        receipt_rows, travel_days, rules
    )

    receipt_result_rows = receipts_after_per_diem + synthetic
    receipt_result_rows = flag_violations(receipt_result_rows, rules, contractor)

    invoice_result_rows = apply_substantiation(invoice_rows, rules)
    held_rows = [r for r in invoice_result_rows if r.get("substantiation_status") == "receipt_required"]
    attested_rows = [r for r in invoice_result_rows if r.get("substantiation_status") == "invoice_attested"]

    all_rows = receipt_result_rows + invoice_result_rows

    # Reimbursable = receipt rows + per-diem + attested invoice lines. Held
    # invoice lines (receipt_required) stay at $0 and are tracked as pending.
    total_extracted = sum(float(r.get("amount") or 0) for r in receipt_rows)
    total_reimbursable = sum(float(r.get("reimbursable_amount") or 0) for r in all_rows)
    total_per_diem_added = sum(
        float(r.get("amount") or 0) for r in synthetic
    )
    # flag_count/flagged_amount cover receipt-side review items only; held
    # invoice lines are reported separately under pending verification.
    flag_count = sum(1 for r in receipt_result_rows if r.get("flagged"))
    flagged_amount = sum(
        float(r.get("reimbursable_amount") or 0)
        for r in receipt_result_rows
        if r.get("flagged")
    )
    pending_verification_amount = sum(float(r.get("amount") or 0) for r in held_rows)
    pending_verification_count = len(held_rows)
    invoice_attested_amount = sum(float(r.get("reimbursable_amount") or 0) for r in attested_rows)
    invoice_attested_count = len(attested_rows)

    warnings = []
    per_diem_rules = rules.get("per_diem", {})
    if per_diem_rules.get("incidentals_includes_pending_partner_review"):
        warnings.append(
            "Per-diem incidentals list (in-flight wifi) is pending Spark partner review. "
            "Currently treating wifi as a per-diem incidental (not separately reimbursable on travel days)."
        )
    if rules.get("status", "").startswith("draft"):
        warnings.append(
            f"Rules version {rules.get('version', '?')} is marked '{rules['status']}'. "
            f"Do NOT process real reimbursements until partner review is complete."
        )
    if pending_verification_count:
        invoice_numbers = sorted({
            str(r.get("invoice_number")) for r in held_rows if r.get("invoice_number")
        })
        inv_ref = f" (invoice {', '.join(invoice_numbers)})" if invoice_numbers else ""
        warnings.append(
            f"{pending_verification_count} invoice line(s) totaling {round(pending_verification_amount, 2)}"
            f"{inv_ref} require a receipt before payment (lodging, airfare, or at/over the "
            f"${rules.get('substantiation', {}).get('receipt_required_over_usd', '?')} threshold). "
            f"Held out of the reimbursable total — request the underlying receipts."
        )
    if invoice_attested_count:
        warnings.append(
            f"{invoice_attested_count} invoice line(s) totaling {round(invoice_attested_amount, 2)} "
            f"were reimbursed on ATTESTATION (under threshold, non-lodging/airfare) without a receipt, "
            f"per the substantiation policy."
        )

    return {
        "receipts": all_rows,
        "summary": {
            "travel_days": sorted(travel_days),
            "n_travel_days": len(travel_days),
            "total_extracted": round(total_extracted, 2),
            "total_reimbursable": round(total_reimbursable, 2),
            "total_per_diem_added": round(total_per_diem_added, 2),
            "total_replaced_by_per_diem": round(total_replaced, 2),
            "net_per_diem_impact": round(total_per_diem_added - total_replaced, 2),
            "flag_count": flag_count,
            "flagged_amount": round(flagged_amount, 2),
            "pending_verification_amount": round(pending_verification_amount, 2),
            "pending_verification_count": pending_verification_count,
            "invoice_attested_amount": round(invoice_attested_amount, 2),
            "invoice_attested_count": invoice_attested_count,
        },
        "warnings": warnings,
    }
