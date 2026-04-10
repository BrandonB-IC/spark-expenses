# Spark Expense Engine

Autonomous expense processing pipeline for Spark contractors. Receipts go in a Google Drive folder; weekly reports come out for Brandon's approval.

**Status:** v1 in setup. See "Setup Progress" section below.

---

## What it does

1. Contractor drops receipts into their Google Drive folder (`Spark Expenses/Contractors/[Name]/[Project]/`)
2. Every Friday at 4 PM, Windows Task Scheduler runs `expense_processor.py`
3. The processor:
   - Lists new receipts (compares against `ledger.json` SHA-256 hashes)
   - OCRs each one with Claude Haiku vision (~$0.003/receipt)
   - Applies Spark's compliance rules (per-diem, hotel cap, airfare tiers, large-item flag)
   - Generates a Markdown summary, CSV ledger, and audit packet PDF
   - Emails the report to Brandon
4. Brandon reviews via Flask dashboard at `http://localhost:8770` and approves/flags items

---

## Setup Progress

- [x] Project scaffolding (folders, configs, auth helpers)
- [x] `.env.template`, `.gitignore`, `requirements.txt`
- [x] `google_auth.py` + `auth_unified.py` (drive.readonly scope)
- [x] `EXPENSE_PRD.md` (PRD reference)
- [x] `CLAUDE.md` (project conventions)
- [x] **Brandon:** Create Google Drive folder structure ✅
- [x] **Brandon:** Create Google Cloud OAuth client + download `credentials.json` ✅
- [x] **Brandon:** Run `python auth_unified.py` to mint `token.json` ✅
- [x] `pipeline/` modules (drive_reader, hasher, vision_extractor, rules_engine, currency, report_builder) ✅
- [x] `scheduler/expense_processor.py` + `.bat` wrapper ✅
- [x] `dashboard/app.py` Flask UI ✅
- [x] `.claude/skills/process-expenses/` skill ✅
- [x] Real-world test with 6 actual receipts (San Diego trip) — $908.60 reimbursable, 7 receipts extracted, 2 flagged ✅
- [ ] **Brandon:** Set home airport in `config/contractors.json` (currently `XXX` placeholder — needed before processing real airfare receipts)
- [ ] **Brandon:** Add Windows Task Scheduler entry (see Manual Setup #5 below)
- [ ] **Brandon:** Review rules with Spark partners (Peter/Dan/David); update changelog

---

## Cost Estimate (be honest)

Per Brandon's preference for cost transparency:

- **Per-receipt OCR cost:** ~$0.003 with Haiku, ~$0.01–0.03 with Sonnet
- **Monthly recurring (estimated 50–100 receipts/month):** $0.15–$3.00
- **Initial backfill (one-time, if processing historical receipts):** depends on volume; budget ~$5–$30 for 1,000 historical receipts
- **No other API costs** — Google Drive API is free, exchangerate.host FX API is free
- **No hosting costs** — runs locally on your laptop via Windows Task Scheduler

---

## Manual Setup Steps

These steps require Brandon (browser-based OAuth, account creation, file uploads). Claude will walk through each one step-by-step in a chat session.

### 1. Create Google Drive folder structure

Open Google Drive (drive.google.com) signed in as `improvement.science@gmail.com`. Create this folder hierarchy:

```
Spark Expenses              ← top-level folder
└── Contractors
    └── Brandon
        ├── NDL-2026
        ├── WHI
        └── General
```

After creating "Spark Expenses", open it and **copy the URL**. The folder ID is the long string at the end:
```
https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz
                                       └─────── this part ──────┘
```

Paste it into `.env` as `SPARK_DRIVE_PARENT_FOLDER_ID`.

### 2. Create Google Cloud OAuth client

This project uses a **separate OAuth client** from the EA — keeps risk isolated so a bug here can't break the EA's calendar/email/drive auth.

Step-by-step (Claude will walk you through this):
1. Go to https://console.cloud.google.com
2. Create a new project: "Spark Expense Engine"
3. Enable the Google Drive API
4. Configure the OAuth consent screen (External, Testing mode, add your email as a test user)
5. Create OAuth 2.0 Client ID (Desktop application type)
6. Download the client secret JSON, rename to `credentials.json`, place in this project folder

### 3. Mint the OAuth token

```bash
cd "c:/Users/impro/Brandon_Claude playground/3.0 spark-expenses"
python auth_unified.py
```

A browser window opens. Sign in as `improvement.science@gmail.com`, authorize the app, then close the browser. `token.json` will be saved next to `auth_unified.py`.

### 4. Drop test receipts

For first-run testing, drop 2–3 receipts into one of your project folders (e.g., a coffee receipt + a hotel receipt + an airfare receipt to test all three rule types).

### 5. Add Windows Task Scheduler entry

Open PowerShell **as Administrator** and paste this single command. It creates a task named "Spark Expense Processor" that runs every Friday at 4:00 PM, retries if your laptop is asleep, and logs to `scheduler/logs/expense_processor.log`:

```powershell
$action = New-ScheduledTaskAction -Execute "c:\Users\impro\Brandon_Claude playground\3.0 spark-expenses\scheduler\run_expense_processor.bat"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At 4:00pm
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "Spark Expense Processor" -Action $action -Trigger $trigger -Settings $settings -Description "Spark Expense Engine weekly run"
```

**To verify it was created:**
```powershell
Get-ScheduledTask -TaskName "Spark Expense Processor"
```

**To trigger it manually for testing:**
```powershell
Start-ScheduledTask -TaskName "Spark Expense Processor"
```

**To delete it later (if you ever want to):**
```powershell
Unregister-ScheduledTask -TaskName "Spark Expense Processor" -Confirm:$false
```

**Why `StartWhenAvailable`:** if your laptop is asleep at exactly 4pm Friday, the task runs the next time the laptop wakes up (instead of just being skipped).

### 6. Review rules with Spark partners

Open `config/expense-rules.json`, walk through it with Peter/Dan/David, then update the file and add an entry to `config/expense-rules-changelog.md` documenting what was decided and why.

---

## Running

**Manual run (any time):**
```bash
python scheduler/expense_processor.py --contractor Brandon
```

**Dry run (no email, no ledger writes):**
```bash
python scheduler/expense_processor.py --contractor Brandon --dry-run
```

**Specific week:**
```bash
python scheduler/expense_processor.py --contractor Brandon --week 2026-W15
```

**Interactive mode (via Claude Code skill):**
```
/process-expenses
```

**Dashboard:**
```bash
python dashboard/app.py
# Browser opens to http://localhost:8770
```

---

## See Also

- `EXPENSE_PRD.md` — original PRD
- `CLAUDE.md` — conventions for Claude Code sessions
- `config/expense-rules-changelog.md` — policy decision history
- Implementation plan: `C:\Users\impro\.claude\plans\temporal-dancing-bear.md`
