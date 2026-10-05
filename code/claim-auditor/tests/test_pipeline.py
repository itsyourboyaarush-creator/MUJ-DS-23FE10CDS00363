"""Offline tests: a fake Anthropic client stands in for the API."""

import json
from types import SimpleNamespace

import pytest

from claim_auditor.config import load_prompts
from claim_auditor.llm import LLMClient, LLMError, parse_json
from claim_auditor.pipeline import Claim, ClaimAuditor, quote_in_source

SOURCE = "A study of 48 workers found coffee drinkers felt more alert. It lasted six weeks."


class FakeAnthropic:
    """Returns scripted replies in order; mimics client.messages.create."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.messages = SimpleNamespace(create=self._create)
        self.calls = 0

    def _create(self, **kwargs):
        self.calls += 1
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=r)],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def make(replies, **kw):
    return LLMClient(model="fake", client=FakeAnthropic(replies), max_retries=2, **kw)


def test_gemini_provider_path():
    pytest.importorskip("google.genai")

    class FakeGemini:
        def __init__(self):
            self.models = SimpleNamespace(generate_content=self._gen)
            self.kwargs = None

        def _gen(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(text='{"ok": true}',
                                   usage_metadata=SimpleNamespace(prompt_token_count=7, candidates_token_count=3))

    fake = FakeGemini()
    llm = LLMClient(model="gemini-3-flash-preview", provider="gemini", client=fake)
    assert llm.complete_json("sys", "usr") == {"ok": True}
    assert fake.kwargs["model"] == "gemini-3-flash-preview" and fake.kwargs["contents"] == "usr"
    assert (llm.usage.input_tokens, llm.usage.output_tokens) == (7, 3)


def test_unknown_provider_rejected():
    with pytest.raises(ValueError):
        LLMClient(model="x", provider="nope", client=object())


def test_parse_json_handles_fences_and_prose():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! {"a": 2} hope that helps') == {"a": 2}
    with pytest.raises(ValueError):
        parse_json("no json here")


def test_repair_retry_on_malformed_json():
    llm = make(["not json", '{"ok": true}'])
    assert llm.complete_json("s", "u") == {"ok": True}
    assert llm.usage.calls == 2


def test_gives_up_after_bad_repair():
    with pytest.raises(LLMError):
        make(["bad", "still bad"]).complete_json("s", "u")


def test_retries_transient_errors(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    err = Exception("boom")
    err.status_code = 529
    llm = make([err, '{"ok": 1}'])
    assert llm.complete_json("s", "u") == {"ok": 1}


def test_non_retryable_error_fails_fast():
    err = Exception("bad request")
    err.status_code = 400
    with pytest.raises(LLMError):
        make([err]).complete_json("s", "u")


def test_cache_avoids_second_call(tmp_path):
    llm = make(['{"x": 1}'], cache_dir=tmp_path)
    llm.complete_json("s", "u")
    llm.complete_json("s", "u")
    assert llm.usage.calls == 1 and llm.usage.cache_hits == 1


def test_quote_check_normalises_whitespace_and_case():
    assert quote_in_source("coffee drinkers   felt MORE alert", SOURCE)
    assert not quote_in_source("coffee extends lifespan", SOURCE)
    assert not quote_in_source("", SOURCE)


def test_fabricated_quote_downgrades_verdict():
    reply = json.dumps({"verdict": "supported", "evidence_quote": "coffee extends lifespan",
                        "issues": ["none"], "confidence": 0.9, "rationale": "r", "rewrite": ""})
    auditor = ClaimAuditor(make([reply]), load_prompts())
    a = auditor.audit_claim(Claim(1, "Coffee extends life"), SOURCE)
    assert a.verdict == "partially_supported"
    assert "quote_not_found_in_source" in a.issues and a.evidence_quote == ""


def test_grounded_supported_claim_kept():
    reply = json.dumps({"verdict": "supported", "evidence_quote": "coffee drinkers felt more alert",
                        "issues": [], "confidence": 0.8, "rationale": "r", "rewrite": ""})
    a = ClaimAuditor(make([reply]), load_prompts()).audit_claim(Claim(1, "Coffee increases alertness"), SOURCE)
    assert a.verdict == "supported" and a.grounded


def test_run_batches_audits_without_dropping_claims():
    extract = json.dumps({"claims": [{"id": claim_id, "text": f"Claim {claim_id}", "type": "empirical"}
                          for claim_id in range(1, 5)]})

    def audit_batch(claim_ids):
        return json.dumps({"audits": [{"id": claim_id, "verdict": "unsupported",
                                       "evidence_quote": "", "issues": [], "confidence": 0.8,
                                       "rationale": "No support found.", "rewrite": ""}
                           for claim_id in claim_ids]})

    replies = [extract, audit_batch([1, 2, 3]), audit_batch([4]), '{"summary": "Reviewed."}']
    llm = make(replies)
    report = ClaimAuditor(llm, load_prompts(), max_workers=1, audit_batch_size=3).run(SOURCE)

    assert len(report.audits) == 4
    assert all(not audit.error for audit in report.audits)
    assert llm.usage.calls == 4


def test_invalid_verdict_and_confidence_are_sanitised():
    reply = json.dumps({"verdict": "banana", "evidence_quote": "", "confidence": "high"})
    a = ClaimAuditor(make([reply]), load_prompts()).audit_claim(Claim(1, "x"), SOURCE)
    assert a.verdict == "unsupported" and a.confidence == 0.0


def test_full_run_scores_and_summarises():
    extract = json.dumps({"claims": [{"id": 1, "text": "Coffee boosts alertness", "type": "causal"}]})
    audit = json.dumps({"audits": [{"id": 1, "verdict": "overstated",
                                    "evidence_quote": "a study of 48 workers",
                                    "issues": ["small_sample"], "confidence": 0.7,
                                    "rationale": "r", "rewrite": "w"}]})
    summary = json.dumps({"summary": "Weak evidence."})
    report = ClaimAuditor(make([extract, audit, summary]), load_prompts()).run(SOURCE)
    assert report.score == 30.0 and report.summary == "Weak evidence."
    assert report.audits[0].issues == ["small_sample"]


def test_empty_input_rejected():
    with pytest.raises(ValueError):
        ClaimAuditor(make([]), load_prompts()).run("   ")
