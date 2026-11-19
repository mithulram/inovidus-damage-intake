"""Server seal for case records.

A proposal (status, match, urgency, task …) is only trusted if THIS server produced it. Every case the
server hands out carries an HMAC over its full content; a case that comes back (next n8n step, store
into the review list) must still carry a valid seal. Version stamps alone do not authenticate a decision.

Key: INTAKE_SIGNING_KEY if set, otherwise a random key per server start (in-flight n8n runs are then
simply re-processed after a restart).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets

from .models import CaseRecord


class Sealer:
    def __init__(self, key: str | bytes | None = None):
        key = key or os.getenv("INTAKE_SIGNING_KEY") or secrets.token_hex(32)
        self._key = key.encode() if isinstance(key, str) else key

    def _digest(self, case: CaseRecord) -> str:
        payload = case.model_dump(mode="json", exclude={"processing": {"signature"}})
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        return "hmac-sha256:" + hmac.new(self._key, raw, hashlib.sha256).hexdigest()

    def seal(self, case: CaseRecord) -> CaseRecord:
        case.processing.signature = self._digest(case)
        return case

    def verify(self, case: CaseRecord) -> bool:
        given = case.processing.signature or ""
        return bool(given) and hmac.compare_digest(given, self._digest(case))
