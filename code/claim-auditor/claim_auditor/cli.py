"""Command line entry point:  python -m claim_auditor.cli samples/health_blog.txt"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .config import load_config, load_prompts
from .llm import LLMClient, LLMError
from .pipeline import ClaimAuditor
from .report import write_reports


KEY_VARS = {"anthropic": ("ANTHROPIC_API_KEY",), "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY")}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="claim-auditor", description="Audit the claims in a text with an LLM.")
    p.add_argument("input", nargs="?", help="text file to audit (default: stdin)")
    p.add_argument("--config", help="path to config.yaml")
    p.add_argument("--prompts", help="path to prompts.yaml")
    p.add_argument("--out", help="output directory (overrides config)")
    p.add_argument("--no-cache", action="store_true", help="disable the on-disk response cache")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")

    try:  # optional convenience: load a local .env if python-dotenv is installed
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    cfg, prompts = load_config(args.config), load_prompts(args.prompts)
    provider = cfg["llm"]["provider"]
    key_vars = KEY_VARS.get(provider, ())
    if not key_vars:
        print(f"error: unknown provider {provider!r} (use anthropic or gemini)", file=sys.stderr)
        return 2
    if not any(os.environ.get(v) for v in key_vars):
        print(f"error: set {' or '.join(key_vars)} (see .env.example)", file=sys.stderr)
        return 2
    if args.input:
        text, stem = Path(args.input).read_text(encoding="utf-8"), Path(args.input).stem
    else:
        text, stem = sys.stdin.read(), "stdin"

    cache_on = cfg["cache"]["enabled"] and not args.no_cache
    llm_cfg = cfg["llm"]
    llm = LLMClient(provider=provider, model=llm_cfg["model"], max_tokens=llm_cfg["max_tokens"],
                    temperature=llm_cfg["temperature"], max_retries=llm_cfg["max_retries"],
                    timeout_s=llm_cfg["timeout_s"],
                    cache_dir=cfg["cache"]["dir"] if cache_on else None)
    pc = cfg["pipeline"]
    auditor = ClaimAuditor(llm, prompts, max_claims=pc["max_claims"],
                           max_workers=pc["max_workers"], max_input_chars=pc["max_input_chars"],
                           audit_batch_size=pc["audit_batch_size"])

    try:
        report = auditor.run(text)
    except (LLMError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    md, js = write_reports(report, args.out or cfg["output"]["dir"], stem)
    u = llm.usage
    print(f"Evidence score: {report.score}/100 across {len(report.audits)} claims")
    print(f"Report: {md}  |  Data: {js}")
    print(f"LLM calls: {u.calls} (+{u.cache_hits} cached) | tokens in/out: {u.input_tokens}/{u.output_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
