"""
One-off helper: convert a markdown file to a clean, print-ready PDF using
Microsoft Edge in headless mode. Edge ships with Windows so this needs no
extra binaries.

Usage:
    python scripts/md_to_pdf.py <input.md> [output.pdf]
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

CSS = """
@page { size: Letter; margin: 0.4in 0.55in; }
html, body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
             color: #222; font-size: 9.5pt; line-height: 1.3; }
h1 { font-size: 15pt; margin: 0 0 0.15em 0; border-bottom: 2px solid #2a7d4f; padding-bottom: 3px; }
h2 { font-size: 11pt; margin: 0.55em 0 0.15em 0; color: #2a7d4f; }
p { margin: 0.2em 0; }
li { margin: 0.1em 0; }
ul { padding-left: 1.1em; margin: 0.15em 0 0.3em 0; }
strong { color: #1a1a1a; }
code { background: #f3f3f3; padding: 0 3px; border-radius: 3px; font-size: 8.8pt; }
"""

def render(md_path: Path, pdf_path: Path) -> None:
    text = md_path.read_text(encoding="utf-8")
    body = markdown.markdown(text, extensions=["extra", "sane_lists"])
    html = f"<!doctype html><meta charset='utf-8'><style>{CSS}</style>{body}"

    with tempfile.NamedTemporaryFile(
        "w", suffix=".html", delete=False, encoding="utf-8"
    ) as f:
        f.write(html)
        html_path = Path(f.name)

    try:
        subprocess.run(
            [
                EDGE,
                "--headless",
                "--disable-gpu",
                f"--print-to-pdf={pdf_path}",
                "--no-pdf-header-footer",
                html_path.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        html_path.unlink(missing_ok=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: md_to_pdf.py <input.md> [output.pdf]")
        sys.exit(1)
    src = Path(sys.argv[1]).resolve()
    dst = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else src.with_suffix(".pdf")
    render(src, dst)
    print(f"wrote {dst}")
