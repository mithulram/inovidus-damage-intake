"""Hosted demo protection (Render): password for people, token for n8n, health check open."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from intake.actions import AuditLog
from intake.store import CaseStore
from intake.web.app import create_app


def client(tmp_path, monkeypatch, password="geheim", token="n8n-token"):
    monkeypatch.setenv("INTAKE_ACCESS_PASSWORD", password)
    monkeypatch.setenv("INTAKE_SERVICE_TOKEN", token)
    return TestClient(create_app(store=CaseStore(tmp_path / "c"), audit=AuditLog(tmp_path / "a.jsonl"), static_dir=tmp_path))


def basic(pw):
    return {"Authorization": "Basic " + base64.b64encode(f"demo:{pw}".encode()).decode()}


def test_health_open_everything_else_protected(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    assert c.get("/api/health").status_code == 200
    for path in ("/", "/api/scenarios", "/api/cases", "/api/rules"):
        r = c.get(path)
        assert r.status_code == 401 and "WWW-Authenticate" in r.headers
    assert c.post("/api/approve", json={}).status_code == 401


def test_password_and_service_token(tmp_path, monkeypatch):
    c = client(tmp_path, monkeypatch)
    assert c.get("/api/scenarios", headers=basic("geheim")).status_code == 200
    assert c.get("/api/scenarios", headers=basic("falsch")).status_code == 401
    assert c.get("/api/scenarios", headers={"x-intake-token": "n8n-token"}).status_code == 200
    assert c.get("/api/scenarios", headers={"x-intake-token": "falsch"}).status_code == 401


def test_open_when_not_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("INTAKE_ACCESS_PASSWORD", raising=False)
    monkeypatch.delenv("INTAKE_SERVICE_TOKEN", raising=False)
    c = TestClient(create_app(store=CaseStore(tmp_path / "c"), audit=AuditLog(tmp_path / "a.jsonl"), static_dir=tmp_path))
    assert c.get("/api/scenarios").status_code == 200
