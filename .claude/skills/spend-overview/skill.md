---
name: spend-overview
description: Generate the Spark spend-by-project x person overview (who spent what against which project). Use when Brandon says "spend overview", "spend by project", "who spent what", "/spend-overview", or asks how much a project or person has cost.
---

# Spend Overview Skill

Regenerates the standalone spend-overview HTML — a project x person matrix where each
cell splits into reimbursed / outstanding / awaiting-receipts — and surfaces it to Brandon.

## When to invoke

- Brandon says "spend overview", "spend by project", "who spent what", "/spend-overview"
- Brandon asks how much a project (NDL, WHI, General) or a person has cost so far
- After a processing run, if Brandon wants the cross-project picture (the weekly email is per-person)

## Steps

### 1. Regenerate the file

```bash
cd "c:/Users/impro/Brandon_Claude playground/3.0 spark-expenses"
python reporting/build_spend_overview.py
```

Writes `reports/spend-overview.html` (self-contained; opens directly in a browser).
It also refreshes automatically at the end of every `expense_processor.py` run, so it is
usually already current — regenerate if claims were just marked paid or new receipts landed.

### 2. Surface it

Send Brandon the file (`reports/spend-overview.html`) rendered so he can see the matrix.
Call out the headline numbers: grand total, outstanding (owed), and awaiting-receipts (held).

### 3. Offer next actions

- Mark outstanding claims paid at the dashboard `/outstanding`, then regenerate to see the shift to "reimbursed".
- Review held invoice lines at `/pending`.

## What the numbers mean

- Amounts are **reimbursable dollars** (what Spark pays), not gross receipts.
- **Outstanding** = verified and owed; **reimbursed** = paid; **awaiting receipts** = invoice lines held pending substantiation (not yet owed).
- Data sources: `reimbursements.json` (claims + paid status), `ledger.json` (sha -> project attribution), `pending_invoices.json` (held lines).
- Multi-project weekly claims are attributed across projects in proportion to ledger extracted amounts (an estimate; single-project weeks are exact). This caveat is printed on the page.

## Files this skill touches

- Reads: `reimbursements.json`, `ledger.json`, `pending_invoices.json`, `config/contractors.json`
- Writes: `reports/spend-overview.html`

## Project location

`c:\Users\impro\Brandon_Claude playground\3.0 spark-expenses\`
