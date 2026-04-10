# PROJECT REQUIREMENTS DOCUMENT (PRD)

**Project:** Autonomous Expense & Reimbursement Engine

> Source: original PRD PDF, converted to markdown 2026-04-10. This is the canonical reference for the engine's mission and constraints. For implementation details, see [CLAUDE.md](CLAUDE.md) and the plan file at `C:\Users\impro\.claude\plans\temporal-dancing-bear.md`.

---

## 1. MISSION & SCOPE

**Objective:** To build an AI-driven expense pipeline that allows contractors to upload receipts to Google Drive and automatically generates itemized, audited expense reports for Administrator approval.

**Guiding Principle:** Minimal effort for contractors; 100% audit-readiness for the organization.

---

## 2. SYSTEM ARCHITECTURE

- **Storage (Source of Truth):** Google Drive folders.
  - `[Org_Root]/Contractors/[Contractor_Name]/Inbox`
  - `[Org_Root]/Contractors/[Contractor_Name]/Archive`
- **Logic Layer:** Claude Code (Agentic Workflow).
- **Database:** `ledger.json` (Local/Cloud file) to store SHA-256 file hashes, preventing duplicate reimbursements.
- **Notification:** Slack Webhook or Email via Python script.

> **Implementation note:** This v1 omits the Inbox/Archive split because Brandon's standing rule is **never delete or move files in Google Drive**. Receipts stay where contractors put them; `ledger.json` tracks which have been processed via SHA-256 hash, achieving the same dedup goal without write access to Drive.

---

## 3. COMPLIANCE & ACCOUNTABLE PLAN RULES

To maintain IRS/Tax compliance, the AI Agent must apply the following logic:

| Category | Rule | Action |
|---|---|---|
| Travel (Air/Hotel) | Direct Reimbursement | Extract exact total; flag if Hotel > $400/night. |
| Meals & Incidentals | Per Diem Only | **Do not reimburse receipts.** Apply flat $55/day if travel is detected. |
| Project Coding | Folder-based | Inherit Project ID from the parent folder name. |
| Thresholds | Large Expense | Flag any single item > $500 for "Manual Review." |
| Currency | Multi-currency | Use transaction date rate; fallback to month-start rate. |

> **Implementation note:** Spark's actual numbers (per Brandon, 2026-04-10) are **per-diem $100/day, hotel $300/night**, with a tiered airfare cap (`$400/$600/$900` by distance) and a 14-day advance booking rule. PRD numbers above are for reference only. Live rules live in `config/expense-rules.json` and changes are logged in `config/expense-rules-changelog.md`. Rules are flagged "draft — pending Spark partner review" until confirmed with Peter/Dan/David.

---

## 4. TECHNICAL SPECIFICATIONS

### A. OCR & Data Extraction
- Extract: Date, Merchant, Category, Currency, Amount, Tax, and "Itemization Status."
- Flag "Credit Card Slips" that lack line-item detail.

### B. Workflow Triggers
- **On-Demand:** Execute via terminal: `claude "process --contractor [Name]"`
- **Scheduled:** GitHub Action to run every Friday at 4:00 PM.

> **Implementation note:** This v1 uses **Windows Task Scheduler** instead of GitHub Actions, matching Brandon's existing automation pattern (morning brief, invoice scheduler, second brain sync, weekly brief). Cloud deployment may come in v2.

### C. Output Deliverables
1. **Reimbursement Summary:** A Markdown dashboard highlighting "Approved" vs "Flagged" items.
2. **Accounting Ledger:** A `.csv` file formatted for import into accounting software.
3. **Audit Packet:** A merged PDF or folder of all processed receipt images.

---

## 5. EXECUTION PLAN (FOR CLAUDE CODE)

1. **Phase 1: Environment Setup.** Initialize Git repo, create `.env` for API keys, and set up the Google Drive connection.
2. **Phase 2: State Management.** Write the `ledger.json` logic to ensure no receipt is processed twice.
3. **Phase 3: Vision Pipeline.** Build the image-to-data extraction tool using vision capabilities.
4. **Phase 4: Reporting & Notification.** Script the Markdown summary generator and the admin alert system.
5. **Phase 5: Cloud Deployment.** Configure GitHub Actions for resilient, off-machine execution.

> **Implementation note:** v1 phasing matches the implementation plan's 5-phase order with Phase 5 swapped for "Skill & Polish" — see plan file for details.

---

## 6. SUCCESS CRITERIA

- Contractor spends < 60 seconds (just a file upload).
- Administrator review takes < 2 minutes per report.
- 100% of receipts are archived with a unique ID for audit trails.
