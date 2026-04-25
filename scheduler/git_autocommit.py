"""
Weekly auto-commit + push of the spark-expenses repo to private GitHub.

Runs Fridays ~4:10pm via Task Scheduler (StartWhenAvailable=True catches
up if the laptop was asleep). Designed for safety first, convenience
second:

  1. Pre-commit safety scan: greps staged paths + contents for patterns
     that suggest secrets/financial data. If ANY match, aborts without
     committing and emails Brandon to review manually.
  2. Size check: refuses to commit any file >5MB.
  3. File-count check: refuses to commit if >200 files changed (suggests
     something unusual happened — maybe a sync dumped junk).
  4. Always emails: either "pushed successfully with summary of changes"
     or "aborted — here's why, please review".
  5. Logs everything to scheduler/logs/git_autocommit.log.

Adapted from the EA version (BrandonB-IC/executive-assistant). Key
differences: spark-expenses-specific path patterns (ledger.json,
contractors.json, reports/, partner draft emails, phase test outputs,
real-receipt fixtures), and DROPS the EA's `projects.json` pattern
because this project's `config/projects.json` is an intentionally-tracked
project list (not personal data).
"""

from __future__ import annotations

import os
import re
import smtplib
import subprocess
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent
load_dotenv(REPO_ROOT / ".env")

GMAIL_SENDER = os.getenv("GMAIL_SENDER", "brandon@improvement-science.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
EA_RECIPIENT = os.getenv("EA_RECIPIENT", "brandon@improvement-science.com")

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024
MAX_CHANGED_FILES = 200
EXPECTED_REMOTE_FRAGMENT = "BrandonB-IC/spark-expenses"
PROJECT_LABEL = "spark-expenses"
GITHUB_URL = "https://github.com/BrandonB-IC/spark-expenses"

SUSPICIOUS_PATH_PATTERNS = [
    # Secrets and OAuth
    r"\.env$",
    r"\.env\.",
    r"token.*\.json$",
    r"credentials.*\.json$",
    r"[/\\]secret",

    # Spark-expenses sensitive named files
    r"^ledger\.json$",
    r"[/\\]ledger\.json$",
    r"contractors\.json$",
    r"financial\.json$",
    r"^reports[/\\]",
    r"_email_draft\.md$",
    r"^drafts[/\\]",

    # Test outputs containing real receipt data
    r"phase\d+_results\.json$",
    r"phase\d+_ledger\.csv$",
    r"phase\d+_summary\.md$",
    r"sample_receipts[/\\].*\.(jpg|jpeg|png|pdf)$",

    # Data-shape backstop (defense-in-depth, mirrors EA after 2026-04-25 leak)
    r"\.pdf$",
    r"\.docx$",
    r"\.xlsx$",
    r"\.bak$",
    r"^documents[/\\]",
    r"-dump[/\\]",
    r"-export[/\\]",
]

SUSPICIOUS_CONTENT_PATTERNS = [
    r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY",
    r"AKIA[0-9A-Z]{16}",
    r"sk-ant-api03-[A-Za-z0-9_\-]{20,}",
    r"sk-[A-Za-z0-9]{40,}",
    r"ya29\.[A-Za-z0-9_\-]{20,}",
    r"ghp_[A-Za-z0-9]{30,}",
    r"gho_[A-Za-z0-9]{30,}",
    r'"private_key"\s*:\s*"-----BEGIN',
]

LOG_PATH = REPO_ROOT / "scheduler" / "logs" / "git_autocommit.log"


def log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line, flush=True)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except (PermissionError, OSError):
        pass


def send_email(subject: str, html_body: str) -> None:
    if not GMAIL_APP_PASSWORD:
        log("WARNING: GMAIL_APP_PASSWORD not set; skipping email notification.")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_SENDER
    msg["To"] = EA_RECIPIENT
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_SENDER, EA_RECIPIENT, msg.as_string())


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    return result


def get_candidate_files() -> list[str]:
    untracked = run(
        ["git", "ls-files", "--others", "--exclude-standard"], check=False
    ).stdout.splitlines()
    modified = run(["git", "ls-files", "--modified"], check=False).stdout.splitlines()
    deleted = run(["git", "ls-files", "--deleted"], check=False).stdout.splitlines()
    all_changed = sorted(set(untracked + modified + deleted))
    return [f for f in all_changed if f.strip()]


def scan_paths(files: list[str]) -> list[str]:
    issues = []
    for f in files:
        for pattern in SUSPICIOUS_PATH_PATTERNS:
            if re.search(pattern, f, re.IGNORECASE):
                issues.append(f"path match [{pattern}]: {f}")
                break
    return issues


def scan_sizes(files: list[str]) -> list[str]:
    issues = []
    for f in files:
        full = REPO_ROOT / f
        if full.is_file():
            size = full.stat().st_size
            if size > MAX_FILE_SIZE_BYTES:
                mb = size / (1024 * 1024)
                issues.append(f"oversize ({mb:.1f}MB > 5MB): {f}")
    return issues


def scan_contents(files: list[str]) -> list[str]:
    issues = []
    for f in files:
        full = REPO_ROOT / f
        if not full.is_file():
            continue
        if full.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            text = full.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern in SUSPICIOUS_CONTENT_PATTERNS:
            if re.search(pattern, text):
                issues.append(f"content match [{pattern[:30]}...]: {f}")
                break
    return issues


def send_abort_email(reason: str, files: list[str], issues: list[str]) -> None:
    html = f"""
    <h2 style="color: #c0392b;">{PROJECT_LABEL} auto-commit ABORTED</h2>
    <p><strong>Reason:</strong> {reason}</p>
    <h3>Issues detected</h3>
    <ul>{"".join(f"<li><code>{i}</code></li>" for i in issues)}</ul>
    <h3>All {len(files)} changed files</h3>
    <pre style="background:#f4f4f4;padding:10px;font-size:12px;">{chr(10).join(files[:100])}</pre>
    <p><strong>Nothing was committed or pushed.</strong> Review manually:</p>
    <pre>cd "3.0 spark-expenses"
git status
git diff</pre>
    <p>If the flagged file is legitimately non-sensitive, either add it to
    <code>.gitignore</code> (if it shouldn't be tracked) or commit manually
    after eyeballing it.</p>
    """
    try:
        send_email(
            subject=f"{PROJECT_LABEL} auto-commit ABORTED — manual review needed",
            html_body=html,
        )
        log(f"Abort notification emailed. Reason: {reason}")
    except Exception as e:
        log(f"WARNING: failed to send abort email: {e}")


def send_success_email(commit_sha: str, files: list[str], stat_summary: str) -> None:
    file_list = "\n".join(files[:50])
    more = f"\n... and {len(files) - 50} more" if len(files) > 50 else ""
    html = f"""
    <h2 style="color: #27ae60;">{PROJECT_LABEL} auto-commit successful</h2>
    <p>Weekly backup pushed to <a href="{GITHUB_URL}">GitHub</a>.</p>
    <p><strong>Commit:</strong> <code>{commit_sha}</code></p>
    <h3>Changed files ({len(files)})</h3>
    <pre style="background:#f4f4f4;padding:10px;font-size:12px;">{file_list}{more}</pre>
    <h3>Diff summary</h3>
    <pre style="background:#f4f4f4;padding:10px;font-size:12px;">{stat_summary}</pre>
    """
    try:
        send_email(
            subject=f"{PROJECT_LABEL} auto-commit: {commit_sha[:7]} pushed to GitHub",
            html_body=html,
        )
        log(f"Success notification emailed for {commit_sha[:7]}.")
    except Exception as e:
        log(f"WARNING: failed to send success email: {e}")


def main() -> int:
    log(f"=== {PROJECT_LABEL} git_autocommit starting ===")

    try:
        remote = run(["git", "remote", "get-url", "origin"]).stdout.strip()
        log(f"Remote: {remote}")
        if EXPECTED_REMOTE_FRAGMENT not in remote:
            log("ERROR: unexpected remote URL. Aborting.")
            return 2
    except Exception as e:
        log(f"ERROR: not a git repo or no 'origin' remote: {e}")
        return 2

    files = get_candidate_files()
    log(f"Candidate files: {len(files)}")

    if not files:
        log("Nothing to commit; skipping email.")
        log("=== nothing to do ===")
        return 0

    if len(files) > MAX_CHANGED_FILES:
        reason = f"Too many changed files ({len(files)} > {MAX_CHANGED_FILES})"
        log(f"ABORT: {reason}")
        send_abort_email(reason, files, [reason])
        return 1

    issues = scan_paths(files) + scan_sizes(files) + scan_contents(files)
    if issues:
        reason = f"{len(issues)} safety issue(s) found"
        log(f"ABORT: {reason}")
        for i in issues:
            log(f"  - {i}")
        send_abort_email(reason, files, issues)
        return 1

    log("All safety checks passed. Staging and committing...")
    run(["git", "add", "-A"])

    staged = run(["git", "diff", "--cached", "--name-only"]).stdout.splitlines()
    staged = [s for s in staged if s.strip()]
    if not staged:
        log("After `git add -A`, nothing was staged. Aborting cleanly.")
        return 0

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"Weekly auto-commit: {stamp} ({len(staged)} files)"
    run(["git", "commit", "-m", msg])

    sha = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    stat = run(["git", "show", "--stat", "--format=", sha]).stdout.strip()

    log(f"Committed {sha}. Pushing to origin/main...")
    push_result = run(["git", "push", "origin", "main"], check=False)
    if push_result.returncode != 0:
        log(f"ERROR: push failed. STDERR: {push_result.stderr}")
        send_abort_email(
            f"Push failed (commit {sha[:7]} exists locally but is not on GitHub).",
            staged,
            [f"git push failed: {push_result.stderr.strip()[:300]}"],
        )
        return 1

    log(f"Pushed {sha} successfully.")
    send_success_email(sha, staged, stat[:3000])
    log("=== done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
