#!/usr/bin/env python3
"""Render one of our Markdown docs to a print-ready PDF.

Uses headless Chrome, which is already on this machine, rather than adding a PDF
toolchain. The styling is deliberately plain-but-branded: this goes to executives, so
it has to read as a document, not as a dump of a repository file.

    python scripts/md2pdf.py docs/COMPETITOR-COMPARISON.md out.pdf
"""
from __future__ import annotations

import html
import pathlib
import re
import subprocess
import sys
import tempfile

import markdown

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: A4 landscape; margin: 12mm 10mm 14mm; }
* { box-sizing: border-box; }
body {
  font: 9.6pt/1.5 -apple-system, "Helvetica Neue", Arial, sans-serif;
  color: #1a2233; margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
h1 {
  font-size: 20pt; line-height: 1.15; margin: 0 0 2mm; letter-spacing: -0.02em;
  color: #0f172a;
}
h1 + p { color: #64748b; font-size: 8.6pt; margin: 0 0 6mm; }
h2 {
  font-size: 12.5pt; margin: 8mm 0 2.5mm; padding-bottom: 1.5mm; color: #0f172a;
  border-bottom: 1.6pt solid #5048E5; letter-spacing: -0.01em;
  /* A heading alone at the foot of a page reads as a mistake. */
  break-after: avoid; page-break-after: avoid;
}
h3 { font-size: 10.5pt; margin: 5mm 0 2mm; color: #334155; break-after: avoid; }
p, li { margin: 0 0 2.2mm; }
ol, ul { margin: 0 0 3mm; padding-left: 5mm; }
li { margin-bottom: 1.6mm; }
strong { color: #0f172a; font-weight: 650; }
em { color: #475569; }
code {
  font: 8.6pt ui-monospace, "SF Mono", Menlo, monospace;
  background: #f1f5f9; padding: 0.3mm 1mm; border-radius: 1mm;
}
a { color: #4338ca; text-decoration: none; }
hr { border: 0; border-top: 0.4pt solid #e2e8f0; margin: 6mm 0; }

table {
  width: 100%; border-collapse: collapse; margin: 0 0 4mm;
  font-size: 8pt; line-height: 1.35;
  /* Long tables must be allowed to split, but never mid-row. */
  break-inside: auto;
}
tr { break-inside: avoid; page-break-inside: avoid; }
thead { display: table-header-group; }   /* repeat headers on every page */
th {
  background: #0f172a; color: #fff; font-weight: 600; text-align: left;
  padding: 1.8mm 1.6mm; font-size: 7.8pt; letter-spacing: 0.01em;
  border: 0.4pt solid #0f172a;
}
/* Bold text sets its own dark ink, which is invisible against the dark header row —
   and the header holding our own column is the first thing anyone reads. */
th strong, th em, th code { color: inherit; background: none; }
td { padding: 1.5mm 1.6mm; border: 0.4pt solid #e2e8f0; vertical-align: top; }
/* The row labels carry the question being asked; give them room not to wrap. */
th:first-child, td:first-child { width: 15%; }
/* Our own column, second, is the one being compared against — mark it. */
th:nth-child(2) { background: #5048E5; border-color: #5048E5; }
td:nth-child(2), tbody tr:nth-child(even) td:nth-child(2) { background: #eef2ff; }
tbody tr:nth-child(even) td { background: #f8fafc; }
td:first-child { font-weight: 550; color: #0f172a; }
table code { font-size: 7.4pt; }

blockquote {
  margin: 0 0 4mm; padding: 2.5mm 3.5mm; border-left: 2pt solid #8B5CF6;
  background: #faf8ff; color: #3730a3;
}

.brand {
  display: flex; align-items: baseline; gap: 2.5mm;
  border-bottom: 2.4pt solid #5048E5; padding-bottom: 2mm; margin-bottom: 5mm;
}
.brand .name { font-size: 13pt; font-weight: 700; color: #0f172a; letter-spacing: -0.02em; }
.brand .name span { color: #5048E5; }
.brand .kicker {
  margin-left: auto; font-size: 7.6pt; color: #64748b; text-transform: uppercase;
  letter-spacing: 0.09em;
}
"""

TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<title>{title}</title><style>{css}</style></head><body>
<div class="brand"><div class="name">Server<span>Ally</span></div>
<div class="kicker">{kicker}</div></div>
{body}
</body></html>"""


def render(md_path: pathlib.Path, pdf_path: pathlib.Path,
           kicker: str = "Internal — competitive review") -> None:
    text = md_path.read_text(encoding="utf-8")

    # Our docs open with a blockquote callout that is provenance, not content; it reads
    # as noise at the top of a printed page.
    body = markdown.markdown(
        text, extensions=["tables", "attr_list", "sane_lists", "md_in_html"])

    # The tick marks carry the whole comparison, so give them weight and colour rather
    # than letting them render as pale emoji in a body-text column.
    body = re.sub(r"✅", '<span style="color:#059669;font-weight:700">✔</span>', body)
    body = re.sub(r"⚠️", '<span style="color:#b45309;font-weight:700">▲</span>', body)
    body = re.sub(r"❌", '<span style="color:#dc2626;font-weight:700">✘</span>', body)

    title = re.search(r"^#\s+(.+)$", text, re.M)
    doc = TEMPLATE.format(css=CSS, body=body, kicker=html.escape(kicker),
                          title=html.escape(title.group(1) if title else md_path.stem))

    with tempfile.TemporaryDirectory() as tmp:
        src = pathlib.Path(tmp) / "doc.html"
        src.write_text(doc, encoding="utf-8")
        subprocess.run(
            [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={pdf_path}", f"--user-data-dir={tmp}/profile",
             src.as_uri()],
            check=True, capture_output=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    render(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]),
           *(sys.argv[3:4] or []))
    print(f"wrote {sys.argv[2]}")
