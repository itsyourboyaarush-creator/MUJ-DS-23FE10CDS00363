"""Render a Report as Markdown and JSON."""

from __future__ import annotations

import json
from pathlib import Path

from .pipeline import Report

ICONS = {"supported": "✅", "partially_supported": "🟡", "overstated": "🟠", "unsupported": "❌"}


def to_markdown(report: Report, title: str = "Claim Audit") -> str:
    lines = [f"# {title}", "", f"**Evidence score:** {report.score}/100", "",
             f"{report.summary}", "", "---", ""]
    for a in report.audits:
        lines += [f"## {a.claim.id}. {ICONS[a.verdict]} {a.verdict.replace('_', ' ')}  `{a.claim.type}`",
                  "", f"> {a.claim.text}", ""]
        if a.evidence_quote:
            lines += [f"**Evidence (verified verbatim):** \"{a.evidence_quote}\"", ""]
        if a.rationale:
            lines += [f"**Why:** {a.rationale}", ""]
        if a.issues:
            lines += [f"**Issues:** {', '.join(a.issues)}", ""]
        if a.rewrite:
            lines += [f"**Defensible rewrite:** {a.rewrite}", ""]
        if a.error:
            lines += [f"**Error:** {a.error}", ""]
        lines.append(f"*confidence {a.confidence:.2f}*")
        lines.append("")
    return "\n".join(lines)


def write_reports(report: Report, out_dir: str | Path, stem: str) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md, js = out / f"{stem}.md", out / f"{stem}.json"
    md.write_text(to_markdown(report, f"Claim Audit: {stem}"), encoding="utf-8")
    js.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return md, js
