# Spark Expense Engine: Contractor Guide

A short reference for what to upload, what not to upload, and what the system does with your files. Read once, then forget about it.

## How it works in 30 seconds

Drop receipts into your assigned Google Drive folder. Every Friday afternoon, the engine reads new files, extracts each receipt with AI vision, applies Spark's reimbursement rules, and produces a weekly approval report. You do not need to do anything else. The engine never moves or deletes your files; it just tracks which ones it has already processed.

## Where to put receipts

Inside `Spark Expenses/Contractors/[Your Name]/`, drop each receipt into the project subfolder it belongs to (for example `NDL-2026`, `WHI`, `General`). The engine inherits the project code from the folder name, so filing matters. A WHI receipt dropped into the NDL folder will be coded to NDL.

## DO upload

- Airfare confirmations and itineraries
- Hotel folios (the full itemized stay, not just the booking confirmation)
- Rideshare receipts (Uber, Lyft, taxi)
- Parking, tolls, baggage fees
- Conference fees and supplies bought for a project
- Foreign-currency receipts. The engine converts them automatically.

File formats: PDF, JPG, or PNG. Multi-receipt PDFs are fine (a monthly Uber statement, for example). One receipt per file is ideal but not required.

## DO NOT upload

- **Invoices.** Invoices are what you send Spark to get paid for your time. They are not receipts and they do not belong in this pipeline. Send invoices to Brandon by email the way you always have.
- **Meal receipts on travel days.** Spark applies a flat $100/day per-diem when travel is detected. The engine will extract your meal receipts and then replace them with per-diem, so itemizing your meals is wasted effort.
- **Credit card statements or bank-app screenshots.** Without itemized merchant detail these are flagged as credit-card-slip-only and slow down review.
- **Personal expenses.** If it is not a project expense, it does not belong in the folder.
- **Receipts you have already uploaded.** The engine dedupes by file hash, but renaming a file changes the hash. Do not re-upload "to be safe."
- **Initial Uber, Lyft, or DoorDash receipts when you also have the tip-updated version.** Many apps email you twice: once at booking and again after the tip posts. Upload only the final, tip-updated receipt.

## What the engine ignores or flags

If something non-receipt slips through, no harm done. The engine surfaces it in the weekly report and the administrator handles it:

- Invoices, statements, screenshots without merchant detail: flagged for review
- Receipts with no readable total: flagged
- Duplicate uploads of the same file: skipped silently
- Meal receipts on travel days: extracted, then replaced by the per-diem

## What you will see

The Friday report lists approved items, flagged items (anything over $500, missing data, or unfamiliar to the engine), and per-diem credits for travel days. If something you uploaded is flagged, the administrator will reach out before processing.

## Questions

Email Brandon. Rules are still being finalized with Spark leadership and are subject to change; you will be notified when anything material changes.
