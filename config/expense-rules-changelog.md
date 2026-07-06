# Expense Rules Changelog

This file tracks every change to `expense-rules.json` along with the **why** — partner conversations, policy decisions, real-world data that prompted the change. Brandon's standing rule: **rules cannot change without an entry here**.

Format: `## [version] — YYYY-MM-DD`

---

## [0.1.0-draft] — 2026-04-10

**Status:** DRAFT — pending Spark partner review (Peter, Dan, David). **Not safe for real reimbursements yet.**

**Initial draft values (from Brandon, 2026-04-10):**
- Per-diem: **$100/day** (replaces meal/incidental receipts; flat rate when travel detected)
- Hotel cap: **$300/night** — Brandon flagged this may need to increase; pending partner review
- Airfare: **tiered by distance** with a 14-day advance booking rule:
  - Short haul (<750 mi): $400 cap
  - Medium haul (750–2,000 mi): $600 cap
  - Long haul (>2,000 mi or international): $900 cap
  - Last-minute booking (<14 days advance): caps at $600 regardless of distance
- Large item flag: **$500** any single line item (manual review)
- Currency: **USD default**, non-USD via exchangerate.host using transaction-date rate (fallback: month-start)

**Rationale for tiered airfare (proposed by Claude, accepted by Brandon for v1):**
A flat airfare cap unfairly burdens west-coast contractors traveling east while overpaying for short hops. Tiered caps by distance from the event city are fairer and still bounded. The 14-day advance rule rewards planning and discourages last-minute panic bookings. Both can be tuned after one quarter of real data.

**To do before going live:**
1. Brandon walks Peter/Dan/David through these numbers
2. Confirm or adjust hotel cap (Brandon expects this may need to go up)
3. Confirm airfare tier structure (vs. e.g. flat cap, vs. actual-receipts-with-justification)
4. Confirm per-diem rate ($100/day vs. GSA federal rates which vary by city)
5. **Confirm in-flight wifi treatment** — for v1, in-flight wifi (e.g. United wifi) is rolled into per-diem as an "incidental" (zero separate reimbursement on travel days). Flagged 2026-04-10 by Brandon during Phase 2 smoke test as a partner-review item. Alternative: treat wifi as a separate reimbursable line because it's a work tool, not a personal incidental.
6. Document any changes here as a new version entry
7. Flip `status` field in `expense-rules.json` from `"draft - pending Spark partner review"` to `"approved"`

**Open questions surfaced from Phase 2 smoke test (2026-04-10):**
- **Privacy in audit notes:** vision model captures pickup/dropoff addresses, driver names, ratings. v1 keeps everything (Brandon's call). May need to revisit if reports get shared beyond Brandon + partners.

**Open questions surfaced from Phase 4 build (2026-04-10):**
- **Per-diem vs company debit card meals:** if a contractor is on a trip where any meals are charged directly to the company debit card, the current per-diem logic would still credit the contractor $100/day on those days, effectively double-paying. Brandon flagged this 2026-04-10 as needing leadership input. Possible approaches:
  1. **All-or-nothing:** if any meal on the trip is on company card, no per-diem at all that trip
  2. **Per-meal reduction:** subtract a flat amount per company-card meal from the per-diem total
  3. **Opt-in/out per trip:** contractor declares per-diem vs actuals at submission time
  4. **Status quo + double-pay tolerated:** accept the overlap as small enough not to matter
  Each approach has implications for how the engine detects company-card payments. v1 has NO logic for this — meals are uniformly replaced by per-diem on travel days regardless of payment source. **Must be resolved with Spark partners (Peter/Dan/David) before processing real reimbursements for any trip where company-card meals are possible.**

---

## [0.2.0-draft] — 2026-07-05

**Set by:** Brandon (for v1; pending broader partner review with Peter/Dan/David)
**Conversation date:** 2026-07-05

**Change:** Added a `substantiation` block defining how invoices (as opposed to receipts) are handled.
- `invoice_attestation_accepted: true`
- `receipt_required_categories: ["travel-airfare", "travel-hotel"]`
- `receipt_required_over_usd: 75`

**Why:**
Contractors began uploading **invoices** — self-prepared, itemized expense summaries with no
attached proof-of-payment receipts — into their receipt folders (first live case: Peter
Margolis's June NDL travel invoice, $1,645.36, no receipts). The old pipeline OCR'd invoice
line items as receipts and rolled them straight into "outstanding owed," booking unsubstantiated,
self-asserted amounts as if they were verified — it even booked a phantom $1,845.36 claim
(invoice + auto per-diem) before this was caught.

Brandon's decision (2026-07-05): adopt a **hybrid** stance rather than accept-all or reject-all.
An itemized invoice + the contractor's attestation is an acceptable submission for **small,
low-risk lines**, but **lodging, airfare, and any single line at or over $75 require a receipt**
before payment. The $75 threshold mirrors the IRS accountable-plan substantiation rule (receipts
required for expenses of $75+, and always for lodging). This respects that co-founders shouldn't
have to itemize every small ground-transport receipt, while keeping the engine from blindly
paying big-ticket or allocation-sensitive amounts (e.g. Peter's airfare is billed at 50%, split
with a separate MGB invoice — a receipt is needed to confirm the split).

**Engine behavior:**
- Phase A (commit c5d42a6): all invoice lines held out of reimbursement, flagged pending verification.
- Phase B (this change): invoice lines that are neither lodging/airfare nor >= $75 become reimbursable
  on attestation; the rest stay held as "receipt required."

**Still open (not changed here):**
- Cross-document reconciliation when both an invoice and its receipts are submitted — including how
  allocated/split line items (invoice amount != receipt amount) should reconcile. Surfaced to Brandon
  2026-07-05 as a design decision before building.
- Overall ruleset `status` remains `draft` — per-diem, hotel cap, airfare tiers still pending the
  broader Peter/Dan/David review.

---

## [1.0.0] — 2026-07-05 — APPROVED (out of draft)

**Approved by:** Brandon (2026-07-05)

**Change:** Flipped `status` from `draft - pending Spark partner review` to `approved`; bumped version to 1.0.0. This is the first production ruleset — the engine's reimbursements are no longer "tracking only." Added `approved_date` + `approved_by`; the substantiation block status likewise moved to approved.

**Scope of approval:** everything through [0.2.0-draft] — per-diem ($100/day), hotel cap ($300/night), tiered airfare + 14-day advance rule, $500 large-item flag, credit-card-slip flag, and the hybrid invoice **substantiation** policy (attestation under $75 for non-lodging/airfare; receipts required otherwise).

**Note on previously-open questions:** the items flagged in earlier entries — company-card-meal vs per-diem overlap, whether the hotel cap should rise, and in-flight wifi treatment — are approved **as currently coded** for v1. They are not blockers to going live; any change is a normal future changelog entry + version bump. If Brandon later walks Peter/Dan/David through specific adjustments, log them here.

---

<!-- Template for future entries:

## [0.2.0] — YYYY-MM-DD

**Approved by:** [Brandon + which partners]
**Conversation date:** YYYY-MM-DD

**Changes:**
- [field]: changed from X to Y

**Why:**
[1-3 sentences on the rationale - the conversation that drove the change, the data that prompted it, etc.]

-->
