"""Load config.yaml and prompts.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from string import Template

import yaml

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_PROMPTS = ("system", "extract_claims", "audit_claim", "audit_claims", "summarize")


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["llm"].setdefault("provider", "anthropic")
    if env_provider := os.environ.get("CLAIM_AUDITOR_PROVIDER"):
        cfg["llm"]["provider"] = env_provider
    if env_model := os.environ.get("CLAIM_AUDITOR_MODEL"):
        cfg["llm"]["model"] = env_model
    return cfg


def load_prompts(path: str | Path | None = None) -> dict[str, Template]:
    path = Path(path) if path else ROOT / "prompts.yaml"
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    missing = [k for k in REQUIRED_PROMPTS if k not in raw]
    if missing:
        raise ValueError(f"prompts file missing keys: {missing}")
    return {k: Template(v) for k, v in raw.items()}
