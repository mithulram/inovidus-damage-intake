"""Local review inbox: one atomically replaced JSON file per case."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from .models import CaseRecord
from .rules import ROOT


class CaseStore:
    def __init__(self, path: Path | str = ROOT / "var/cases"):
        self.path = Path(path)

    def _file(self, case_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", case_id):
            raise ValueError("Ungültige Vorgangs-ID")
        return self.path / f"{case_id}.json"

    def save(self, case: CaseRecord) -> CaseRecord:
        target = self._file(case.case_id)
        self.path.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path,
                                             suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(case.model_dump_json(indent=2) + "\n")
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return case

    def get(self, case_id: str) -> CaseRecord | None:
        path = self._file(case_id)
        return CaseRecord.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None

    def list(self) -> list[CaseRecord]:
        cases = [CaseRecord.model_validate_json(p.read_text(encoding="utf-8")) for p in self.path.glob("*.json")]
        return sorted(cases, key=lambda c: (c.received_at.timestamp(), c.case_id), reverse=True)
