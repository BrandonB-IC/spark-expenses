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
