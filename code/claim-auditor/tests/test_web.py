import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from claim_auditor import web


client = TestClient(web.app)


def test_home_and_sample_list():
    home = client.get("/")
    assert home.status_code == 200
    assert "Claim Auditor" in home.text

    samples = client.get("/api/samples")
    assert samples.status_code == 200
    assert all(name.endswith(".txt") for name in samples.json())


def test_sample_path_is_limited_to_text_files():
    with pytest.raises(HTTPException):
        web.read_sample("../config.yaml")
    assert client.get("/api/samples/config.yaml").status_code == 404


def test_audit_endpoint_returns_pipeline_result(monkeypatch):
    expected = {
        "score": 80.0,
        "summary": "Mostly supported.",
        "audits": [],
        "markdown": "# Claim Audit",
        "usage": {"calls": 2, "cache_hits": 1, "input_tokens": 10, "output_tokens": 5},
    }
    monkeypatch.setattr(web, "run_audit", lambda text: expected)

    response = client.post("/api/audit", json={"text": "A short sample."})

    assert response.status_code == 200
    assert response.json() == expected


def test_audit_endpoint_rejects_blank_text():
    response = client.post("/api/audit", json={"text": "   "})
    assert response.status_code == 422