"""Local web interface for the claim-auditor pipeline."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import ROOT, load_config, load_prompts
from .llm import LLMClient, LLMError
from .pipeline import ClaimAuditor
from .report import to_markdown

STATIC_DIR = Path(__file__).parent / "static"
SAMPLES_DIR = ROOT / "samples"
KEY_VARS = {"anthropic": ("ANTHROPIC_API_KEY",), "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY")}

app = FastAPI(title="Claim Auditor", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class AuditRequest(BaseModel):
    text: str = Field(max_length=100_000)


def read_sample(name: str) -> str:
    if Path(name).name != name or not name.lower().endswith(".txt"):
        raise HTTPException(status_code=404, detail="Sample not found")
    path = (SAMPLES_DIR / name).resolve()
    if path.parent != SAMPLES_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Sample not found")
    return path.read_text(encoding="utf-8")


def run_audit(text: str) -> dict:
    load_dotenv(ROOT / ".env")
    cfg, prompts = load_config(), load_prompts()
    llm_cfg = cfg["llm"]
    provider = llm_cfg["provider"]
    key_vars = KEY_VARS.get(provider)
    if key_vars is None:
        raise ValueError(f"Unknown provider {provider!r}; use anthropic or gemini")
    if not any(os.environ.get(key) for key in key_vars):
        raise ValueError(f"Set {' or '.join(key_vars)} in .env before running an audit")

    cache_cfg = cfg["cache"]
    llm = LLMClient(
        provider=provider,
        model=llm_cfg["model"],
        max_tokens=llm_cfg["max_tokens"],
        temperature=llm_cfg["temperature"],
        max_retries=llm_cfg["max_retries"],
        timeout_s=llm_cfg["timeout_s"],
        cache_dir=cache_cfg["dir"] if cache_cfg["enabled"] else None,
    )
    pipeline_cfg = cfg["pipeline"]
    auditor = ClaimAuditor(
        llm,
        prompts,
        max_claims=pipeline_cfg["max_claims"],
        max_workers=pipeline_cfg["max_workers"],
        max_input_chars=pipeline_cfg["max_input_chars"],
        audit_batch_size=pipeline_cfg["audit_batch_size"],
    )
    report = auditor.run(text)
    result = report.to_dict()
    result["markdown"] = to_markdown(report)
    result["usage"] = {
        "calls": llm.usage.calls,
        "cache_hits": llm.usage.cache_hits,
        "input_tokens": llm.usage.input_tokens,
        "output_tokens": llm.usage.output_tokens,
    }
    return result


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/samples")
def list_samples() -> list[str]:
    if not SAMPLES_DIR.is_dir():
        return []
    return sorted(path.name for path in SAMPLES_DIR.glob("*.txt") if path.is_file())


@app.get("/api/samples/{name}")
def get_sample(name: str) -> dict[str, str]:
    return {"name": name, "text": read_sample(name)}


@app.post("/api/audit")
def audit(request: AuditRequest) -> dict:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Paste or load some text first")
    try:
        return run_audit(text)
    except (LLMError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc