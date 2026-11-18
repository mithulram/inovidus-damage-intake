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
    urls = [NODES[n]["parameters"].get("url", "") for n in _chain_from("E-Mail eingegangen")]
    called = [m.group(1) for u in urls if (m := re.search(r"/api/steps/(\w+)", u))]
    assert called == list(STEPS)


def test_inbound_metadata_is_passed_through():
    prep = json.dumps(NODES["E-Mail vorbereiten"]["parameters"])
    for key in ("subject", "body", "sender_email", "message_id", "received_at", "attachments"):
        assert key in prep


def test_workflow_never_approves_sends_or_holds_secrets():
    assert "/api/approve" not in EXECUTABLE  # sticky notes may explain it, nodes may not call it
    assert "$env" not in TEXT
    assert not re.search(r"gsk_[A-Za-z0-9]{8,}", TEXT)
    assert not any(n["type"].endswith(("emailSend", "gmail", "microsoftOutlook")) for n in WF["nodes"] if not n.get("disabled"))


def test_branches_read_only_status_and_urgency():
    for name in ("Notfall?", "Status?"):
        exprs = re.findall(r"\$json\.([\w.]+)", json.dumps(NODES[name]["parameters"]))
        assert set(exprs) <= {"status", "urgency.level"}
