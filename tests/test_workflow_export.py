"""The committed n8n export must stay a pure router over the same steps as /api/process."""

from __future__ import annotations

import json
import re

from intake.rules import ROOT
from intake.steps import STEPS

WF = json.loads((ROOT / "workflows" / "n8n_schadenmeldung.json").read_text(encoding="utf-8"))
NODES = {n["name"]: n for n in WF["nodes"]}
TEXT = json.dumps(WF, ensure_ascii=False)
EXECUTABLE = json.dumps([n for n in WF["nodes"] if n["type"] != "n8n-nodes-base.stickyNote"], ensure_ascii=False)


def _chain_from(start: str) -> list[str]:
    order, current = [], start
    while current in WF["connections"]:
        nxt = WF["connections"][current]["main"][0][0]["node"]
        order.append(nxt)
        current = nxt
    return order


def test_step_nodes_call_every_step_in_pipeline_order():
    urls = [NODES[n]["parameters"].get("url", "") for n in _chain_from("E-mail received (E-Mail eingegangen)")]
    called = [m.group(1) for u in urls if (m := re.search(r"/api/steps/(\w+)", u))]
    assert called == list(STEPS)


def test_inbound_metadata_is_passed_through():
    prep = json.dumps(NODES["Prepare e-mail (E-Mail vorbereiten)"]["parameters"])
    for key in ("subject", "body", "sender_email", "message_id", "received_at", "attachments"):
        assert key in prep


def test_workflow_never_approves_sends_or_holds_secrets():
    assert "/api/approve" not in EXECUTABLE  # sticky notes may explain it, nodes may not call it
    assert "$env" not in TEXT
    assert not re.search(r"gsk_[A-Za-z0-9]{8,}", TEXT)
    assert not any(n["type"].endswith(("emailSend", "gmail", "microsoftOutlook")) for n in WF["nodes"] if not n.get("disabled"))


def test_branches_read_only_status_and_urgency():
    for name in ("Emergency? (Notfall?)", "Which status? (Welcher Status?)"):
        exprs = re.findall(r"\$json\.([\w.]+)", json.dumps(NODES[name]["parameters"]))
        assert set(exprs) <= {"status", "urgency.level"}


def test_every_node_is_bilingual():
    for n in WF["nodes"]:
        if n["type"] == "n8n-nodes-base.stickyNote":
            assert "*DE:" in n["parameters"]["content"], n["name"]      # English first, German after
        else:
            assert "(" in n["name"] and n["name"].rstrip().endswith(")"), n["name"]
            assert n["notes"].startswith("EN: ") and "\nDE: " in n["notes"], n["name"]
        assert not any(ch in n["name"].split("(")[0] for ch in "äöüßÄÖÜ"), n["name"]  # English part comes first


def test_http_nodes_retry_for_cold_starts():
    for n in WF["nodes"]:
        if n["type"] == "n8n-nodes-base.httpRequest":
            assert n.get("retryOnFail") and n["parameters"]["options"]["timeout"] >= 120000


def test_webhook_requires_token_and_returns_only_a_receipt():
    hook = NODES["E-mail received (E-Mail eingegangen)"]
    assert hook["parameters"]["authentication"] == "headerAuth"
    assert hook["credentials"]["httpHeaderAuth"]["id"]
    resp = next(n for n in WF["nodes"] if n["type"] == "n8n-nodes-base.respondToWebhook")
    body = resp["parameters"]["responseBody"]
    for leak in ("match", "candidates", "audit", "prior_cases", "input"):
        assert leak not in body
