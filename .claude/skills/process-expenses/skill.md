---
name: process-expenses
description: Spark Expense Engine — interactive on-demand processing of contractor receipts. Use when Brandon says "process expenses", "run expense report", "/process-expenses", or asks about pending receipts.
---

# Process Expenses Skill

Interactive entry point for the Spark Expense Engine. Walks Brandon through running the expense processor, surfaces what was extracted, and offers next actions.

## When to invoke

- Brandon says "process expenses", "run the expense engine", "let's do expenses", "/process-expenses"
- Brandon mentions a new trip and asks if he should upload receipts
- Brandon asks about flagged items, per-diem totals, or the latest expense report

## Steps

### 1. Confirm intent + week
Ask Brandon which week to process:
- Default: current ISO week (e.g. `2026-W15`)
- He may say "this trip" or "last week" — interpret accordingly
- If unsure, default to current week and note it

### 2. Quick pre-flight check
Before running, confirm:
- `config/contractors.json` exists (not just the template)
- `credentials.json` and `token.json` exist (auth is set up)
- Brandon has dropped receipts into the right Drive folder

If any of these are missing, surface the gap and stop. Don't run a broken pipeline.

### 3. Run the orchestrator with verbose output

```bash
cd "c:/Users/impro/Brandon_Claude playground/3.0 spark-expenses"
python scheduler/expense_processor.py --interactive
```

Optional flags:
- `--contractor brandon` — only process Brandon's folder (faster if multiple contractors are configured)
- `--week 2026-W15` — explicit week label
- `--dry-run` — extraction + report but no ledger writes / no email (use this if Brandon just wants a preview)
- `--no-email` — process + save ledger but skip email

### 4. Stream progress to Brandon
The `--interactive` flag enables debug logging. Show Brandon:
- How many files were found in Drive
- How many were already in the ledger (skipped)
- How many were freshly extracted
- The extraction cost in tokens + dollars
- Whether the report email was sent

### 5. Summarize the result
After the run, fetch and report:
- **Total reimbursable** — the headline number
- **Travel days detected** — confirms per-diem was applied to the right days
- **Items flagged for review** — list each flagged item + reason (don't bury this)
- **Net per-diem impact** — was Brandon under or over actual meal spend?
- **Where the report lives** — `reports/<week>/summary_<contractor>.md` and the dashboard URL

### 6. Offer next actions
Don't stop after reporting. Ask Brandon:
- Want to **open the dashboard** at http://localhost:8770 to review? (Offer to run `python dashboard/app.py` if it's not already running.)
- Want to **mark anything as approved or flagged** beyond what the rules caught?
- Are there **more receipts to upload** before sending the final report?
- Want to **see the audit packet folder** (original PDFs) at `reports/<week>/receipts/<contractor>/`?

## Important reminders

- **Cost honesty:** roughly $0.009 per PDF with Haiku. A typical month of 50–100 receipts costs $0.45–$0.90. Tell Brandon the cost when it's relevant.
- **Rules version:** the rules are still flagged `draft - pending Spark partner review` until Brandon confirms with Peter/Dan/David. Don't let him approve real reimbursements through the dashboard until that conversation happens. Surface the warning banner if it's still there.
- **Dedup is automatic:** SHA-256 hashes in `ledger.json` mean re-running is safe and free for already-processed receipts.
- **Never delete or modify Drive files** — the engine uses readonly scope. If a contractor uploads the wrong file, ask the contractor to delete it from Drive themselves (you can't).
- **Brandon's home airport** — currently a placeholder (`XXX`) in `config/contractors.json`. Until he sets it, all airfare receipts will be flagged "home airport not configured." Remind him gently if relevant.

## Files this skill touches

- Reads: `config/contractors.json`, `config/expense-rules.json`, `config/projects.json`, Drive folder via OAuth
- Writes: `ledger.json`, `reports/<week>/`, `scheduler/logs/expense_processor.log`
- Sends: weekly report email to `brandon@improvement-science.com`

## Project location

`c:\Users\impro\Brandon_Claude playground\3.0 spark-expenses\`

This is a separate project from the EA (which lives at `2.0 executive-assistant`). Use this skill only when Brandon's session is in or about the spark-expenses folder.
