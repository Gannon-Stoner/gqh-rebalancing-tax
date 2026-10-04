"""Render the quant note from its template and a results JSON, then print it to PDF.

Every number in the note is a placeholder ``{{dotted.path:format}}`` resolved against
the results file (list items by index, e.g. ``ci90.0``), so the PDF cannot disagree
with ``python -m gqh.reproduce``. Unresolved placeholders stop the build.

Run:  python scripts/render_note.py results.json      -> note/note.md, note/note.html, note/note.pdf
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "note"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PLACEHOLDER = re.compile(r"\{\{([^}:]+)(?::([^}]*))?\}\}")


def resolve(res: dict, path: str):
    cur = res
    for part in path.strip().split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(f"{path}: no '{part}'")
    return cur


def render(template: str, res: dict) -> str:
    def sub(m: re.Match) -> str:
        val = resolve(res, m.group(1))
        fmt = m.group(2)
        if val is None:
            return "n/a"
        return format(val, fmt) if fmt else str(val)

    out = PLACEHOLDER.sub(sub, template)
    left = PLACEHOLDER.findall(out)
    if left:
        raise SystemExit(f"unresolved placeholders: {left[:5]}")
    return out


def main() -> None:
    res = json.loads(Path(sys.argv[1]).read_text())
    res["calibration"] = json.loads((ROOT / "reports" / "inference_calibration.json").read_text())
    # IS-only diagnostics come from the one-time IS run: in an ALL run, diagnostics pool IS and OOS events (A20)
    is_run = ROOT / "results_is.json"
    res["is_run"] = json.loads(is_run.read_text()) if is_run.is_file() else res
    # Saved aggregate position statistics; rebuilding the audit requires licensed local data.
    # Rendering the supplied results never needs market prices or a trade replay bundle.
    res["pg_size"] = json.loads((ROOT / "reports" / "final_audit.json").read_text())["pg_size"]
    template = (NOTE / "note_template.md").read_text()
    if not res.get("rows_OOS", {}).get("months"):        # before freeze-final: drop the OOS block
        template = re.sub(r"<!--OOS-->.*?<!--/OOS-->", "", template, flags=re.S)
    md = render(template, res)
    markers = re.findall(r"\[\[[^\]]*\]\]", md)
    if markers and "--draft" not in sys.argv:
        raise SystemExit(f"unfinished text markers remain: {markers[:3]}")
    md = re.sub(r"\[\[([^\]]*)\]\]", r'<span style="background:#fff2cc">[pending: \1]</span>', md)
    md = re.sub(r"(?<![\w.\-/])-(?=\d)", "\u2212", md)   # typographic minus for negative numbers (not dates/paths)
    (NOTE / "note.md").write_text(md)
    subprocess.run(["pandoc", str(NOTE / "note.md"), "-o", str(NOTE / "note.html"), "--standalone", "--embed-resources",
                    "--from", "markdown-tex_math_dollars+tex_math_single_backslash", "--mathml",   # \( \) math; $ is money
                    "--css", "note.css", "--metadata", "title=Paying for what is left", "--resource-path", str(ROOT)],
                   check=True, cwd=NOTE)
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={NOTE / 'note.pdf'}", (NOTE / "note.html").as_uri()], check=True,
                   capture_output=True)
    pages = len(re.findall(rb"/Type\s*/Page[^s]", (NOTE / "note.pdf").read_bytes()))
    print(f"note.pdf: {pages} pages")


if __name__ == "__main__":
    main()
