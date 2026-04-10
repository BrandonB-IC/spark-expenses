# CLAUDE.md — Spark Expense Engine

> Read this at the start of every session. It is the source of truth for what this project does and the conventions Claude must follow when working on it.

## Project Overview

The **Spark Expense Engine** is an autonomous expense processing pipeline for Spark contractors. Contractors upload receipts to Google Drive; a Friday-afternoon job OCRs them with Claude vision, applies Spark's compliance rules, and generates a weekly approval report for Brandon (the administrator in v1).

**Owner:** Brandon — sole developer, sole user, sole approver in v1.
**Business:** Spark (NOT ISC LLC). All financial logic, contractor lists, and reports are Spark-only.
**Status:** v1 in active development. See `README.md` for setup state.

## Key Conventions

### Standing rules — DO NOT VIOLATE
- **Never delete or modify files in Google Drive.** This is Brandon's hard rule across all projects. v1 uses `drive.readonly` scope only. Receipts stay where contractors put them; `ledger.json` tracks processed state via SHA-256 hash.
- **Always use `google_auth.load_credentials()` for Google API calls.** Never call `Credentials.from_authorized_user_file()` directly with a narrow scope list — it silently wipes other scopes from `token.json`. The shared helper at the project root manages this.
- **Never commit secrets.** `.env`, `credentials.json`, `token.json`, `config/contractors.json`, `ledger.json`, and `reports/` are gitignored. If you need to add a secret, add to `.gitignore` first.
- **Cost honesty.** When discussing API spend with Brandon, distinguish one-time costs (initial backfill) from recurring costs (per receipt). Brandon was burned once on a "$5/year" estimate that turned into hundreds at setup time.

### Spark-specific compliance rules
Live in `config/expense-rules.json`. **Brandon must consult Spark business partners (Peter/Dan/David) before any rule change goes live.** Every rule change requires an entry in `config/expense-rules-changelog.md` documenting the partner conversation and rationale. Rules are currently flagged "draft — pending partner review."

Current values (2026-04-10):
- Per-diem: $100/day (replaces meal/incidental receipts)
- Hotel cap: $300/night (may need to increase — pending review)
- Airfare: tiered ($400 short / $600 medium / $900 long haul) + 14-day advance booking rule
- Large item flag: $500
- Currency: USD default; non-USD via exchangerate.host

### Technical conventions
- **Python 3.12** on Windows ARM64 (Snapdragon laptop). `pdftoppm` is NOT available — use `pdfplumber` for PDF receipts.
- **Vision model:** `claude-haiku-4-5-20251001` for cost efficiency on bulk OCR (~$0.003/receipt).
- **Standalone token:** This project has its own `credentials.json` and `token.json`, separate from the EA's shared token. Do NOT try to reuse the EA's token here — it lives in a different OAuth client.
- **Dashboard port:** Flask app runs on `8770` (EA dashboard is `8765` — don't collide).
- **Schedule:** Windows Task Scheduler entry "Spark Expense Processor" runs Friday 4:00 PM. Wired via `scheduler/run_expense_processor.bat`.

### CRITICAL: Shared Drive flags on EVERY Drive API call
The `Spark Expenses` parent folder lives in a **Shared Drive** (driveId `0ANGQQnk5Z7teUk9PVA`), NOT in My Drive. Without the right flags, the Drive API behaves as if shared drives don't exist and returns 404 "File not found" for any folder lookup. Every single `files().list()`, `files().get()`, and `files().get_media()` call MUST pass:

```python
supportsAllDrives=True,
includeItemsFromAllDrives=True,  # only on .list() — get/get_media just need supportsAllDrives
```

This was diagnosed during initial Drive API validation on 2026-04-10. The cost was 30 minutes of confused 404s. Bake these flags into `pipeline/drive_reader.py` from day one. If you ever see a 404 when reading from Drive in this project, your first suspicion should be a missing shared-drive flag, not an actual missing file.

### File layout (key files only)
```
3.0 spark-expenses/
├── google_auth.py              # Shared OAuth helper — drive.readonly scope
├── auth_unified.py             # One-time OAuth bootstrap
├── config/
│   ├── contractors.json        # Contractor list (gitignored — has emails + folder IDs)
│   ├── expense-rules.json      # Compliance rules (versioned)
│   ├── expense-rules-changelog.md  # Audit trail of policy changes
│   └── projects.json           # Spark project IDs + display names
├── pipeline/
│   ├── drive_reader.py         # Lists new receipts from Drive
│   ├── hasher.py               # SHA-256 dedup
│   ├── vision_extractor.py     # Claude vision OCR
│   ├── rules_engine.py         # Compliance logic (pure functions)
│   ├── currency.py             # FX conversion
│   └── report_builder.py       # Markdown + CSV + PDF outputs
├── scheduler/
│   ├── expense_processor.py    # Main orchestrator
│   └── run_expense_processor.bat   # Task Scheduler wrapper
├── dashboard/
│   └── app.py                  # Flask mini-dashboard on :8770
├── ledger.json                 # SHA-256 → processing state (gitignored)
└── reports/                    # Per-week output folders (gitignored)
```

## Working Style with Brandon

- **Brandon is non-technical.** He cannot fix code himself. Diagnose and fix everything via tools. Don't ask him to run commands manually unless it's a browser-based OAuth flow that genuinely requires a human.
- **Build a draft, ship it, refine through use.** Don't over-engineer v1. Get something working end-to-end with one test contractor (Brandon himself), then iterate based on real receipts.
- **Be proactive.** If you see a problem, surface it. If you're about to do something that might surprise him, flag it first.

## Reference Projects (do not modify from this project)

- **EA (Executive Assistant):** `c:\Users\impro\Brandon_Claude playground\2.0 executive-assistant\` — Many patterns are copied from here (`google_auth.py`, scheduler + .bat wrapper, skill structure). If you need to update one of those patterns in the EA, do it in a separate session inside that project's folder.
- **LINSIGHT:** `c:\Users\impro\Brandon_Claude playground\1.0 workflows\` — academic research tracker, totally unrelated. Mentioned only because the same Anthropic API key is shared.
