"""Three-stage pipeline: extract claims -> audit each against the source -> summarise."""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from .llm import LLMClient, LLMError

log = logging.getLogger(__name__)

VERDICT_SCORES = {"supported": 1.0, "partially_supported": 0.6, "overstated": 0.3, "unsupported": 0.0}
CLAIM_TYPES = {"empirical", "causal", "comparative", "numeric", "predictive"}


@dataclass
class Claim:
    id: int
    text: str
    type: str = "empirical"


@dataclass
class Audit:
    claim: Claim
    verdict: str = "unsupported"
    evidence_quote: str = ""
    grounded: bool = False          # quote verified verbatim in the source
    issues: list[str] = field(default_factory=list)
    confidence: float = 0.0
    rationale: str = ""
    rewrite: str = ""
    error: str = ""


@dataclass
class Report:
    audits: list[Audit]
    score: float
    summary: str

    def to_dict(self) -> dict:
        return {"score": self.score, "summary": self.summary,
                "audits": [asdict(a) for a in self.audits]}


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_in_source(quote: str, source: str) -> bool:
    q = _norm(quote).strip(" .\"'")
    return bool(q) and q in _norm(source)


class ClaimAuditor:
    def __init__(self, llm: LLMClient, prompts: dict, max_claims: int = 12,
                 max_workers: int = 4, max_input_chars: int = 20000,
                 audit_batch_size: int = 3):
        if audit_batch_size < 1:
            raise ValueError("audit_batch_size must be at least 1")
        self.llm, self.p = llm, prompts
        self.max_claims, self.max_workers = max_claims, max_workers
        self.max_input_chars = max_input_chars
        self.audit_batch_size = audit_batch_size

    def extract_claims(self, text: str) -> list[Claim]:
        user = self.p["extract_claims"].substitute(text=text, max_claims=self.max_claims)
        data = self.llm.complete_json(self.p["system"].template, user)
        claims = []
        for i, c in enumerate(data.get("claims", [])[: self.max_claims], 1):
            body = str(c.get("text", "")).strip()
            if body:
                ctype = c.get("type") if c.get("type") in CLAIM_TYPES else "empirical"
                claims.append(Claim(id=i, text=body, type=ctype))
        return claims

    def audit_claim(self, claim: Claim, text: str) -> Audit:
        user = self.p["audit_claim"].substitute(claim=claim.text, text=text)
        try:
            data = self.llm.complete_json(self.p["system"].template, user)
        except LLMError as exc:
            return Audit(claim=claim, error=str(exc), rationale="Audit failed; treated as unsupported.")
        return self._build_audit(claim, data, text)

    def audit_claims(self, claims: list[Claim], text: str) -> list[Audit]:
        claim_data = [{"id": claim.id, "text": claim.text, "type": claim.type} for claim in claims]
        user = self.p["audit_claims"].substitute(claims=json.dumps(claim_data), text=text)
        try:
            response = self.llm.complete_json(self.p["system"].template, user)
        except LLMError as exc:
            return [Audit(claim=claim, error=str(exc),
                          rationale="Audit failed; treated as unsupported.") for claim in claims]

        entries = response.get("audits", [])
        results_by_id = {}
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                try:
                    claim_id = int(entry.get("id"))
                except (TypeError, ValueError):
                    continue
                if claim_id not in results_by_id:
                    results_by_id[claim_id] = entry

        audits = []
        for claim in claims:
            data = results_by_id.get(claim.id)
            if data is None:
                audits.append(Audit(claim=claim, error="model omitted audit result",
                                     rationale="Batch response did not include this claim."))
            else:
                audits.append(self._build_audit(claim, data, text))
        return audits

    @staticmethod
    def _build_audit(claim: Claim, data: dict, text: str) -> Audit:
        verdict = data.get("verdict") if data.get("verdict") in VERDICT_SCORES else "unsupported"
        quote = str(data.get("evidence_quote", "")).strip()
        grounded = quote_in_source(quote, text)
        raw_issues = data.get("issues", [])
        issues = [str(issue) for issue in raw_issues if issue and issue != "none"] \
            if isinstance(raw_issues, list) else []

        # Grounding check: a "supported" verdict resting on a quote that is not in the source is not trusted.
        if verdict in ("supported", "partially_supported") and not grounded:
            verdict = "partially_supported" if verdict == "supported" else "unsupported"
            issues.append("quote_not_found_in_source")
        try:
            conf = min(1.0, max(0.0, float(data.get("confidence", 0.0))))
        except (TypeError, ValueError):
            conf = 0.0
        return Audit(claim=claim, verdict=verdict, evidence_quote=quote if grounded else "",
                     grounded=grounded, issues=issues, confidence=conf,
                     rationale=str(data.get("rationale", "")), rewrite=str(data.get("rewrite", "")))

    @staticmethod
    def score(audits: list[Audit]) -> float:
        if not audits:
            return 0.0
        return round(100 * sum(VERDICT_SCORES[a.verdict] for a in audits) / len(audits), 1)

    def summarize(self, audits: list[Audit]) -> str:
        slim = [{"claim": a.claim.text, "verdict": a.verdict, "issues": a.issues} for a in audits]
        user = self.p["summarize"].substitute(audits=json.dumps(slim, indent=1))
        try:
            return str(self.llm.complete_json(self.p["system"].template, user).get("summary", ""))
        except LLMError:
            return "Summary unavailable (LLM error)."

    def run(self, text: str) -> Report:
        text = text.strip()
        if not text:
            raise ValueError("input text is empty")
        if len(text) > self.max_input_chars:
            log.warning("input truncated to %d chars", self.max_input_chars)
            text = text[: self.max_input_chars]
        claims = self.extract_claims(text)
        if not claims:
            return Report([], 0.0, "No checkable claims were found in the text.")
        claim_batches = [claims[index:index + self.audit_batch_size]
                         for index in range(0, len(claims), self.audit_batch_size)]
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            batch_results = list(pool.map(lambda batch: self.audit_claims(batch, text), claim_batches))
        audits = [audit for batch in batch_results for audit in batch]
        return Report(audits, self.score(audits), self.summarize(audits))
