"""ERP access behind an interface. The prototype reads JSON seed files; production
would implement :class:`ERPConnector` against the real ERP API (read-only for matching,
writes only after human approval)."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from .rules import ROOT

DATA_DIR = ROOT / "data"


class Contact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str | None = None
    phone: str | None = None
    synthetic: bool = True


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_id: str
    tenant_name: str
    object_id: str
    street: str
    house_no: str
    floor: int | None
    floor_label: str
    side: str | None
    side_label: str
    unit_id: str
    active: bool
    contact: Contact = Contact()

    @property
    def unit_label(self) -> str:
        return f"{self.street} {self.house_no}, {self.floor_label} {self.side_label}".strip()


class Property(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_id: str
    street: str
    house_no: str
    zip: str
    city: str
    caretaker: str | None = None


class ExistingCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    contract_id: str
    unit_id: str
    title: str
    category: str
    room: str | None = None
    state: str
    opened_at: str | None = None
    closed_at: str | None = None
    resolution: str | None = None
    contractor: str | None = None


class ERPConnector(Protocol):
    def contracts(self) -> list[Contract]: ...
    def properties(self) -> list[Property]: ...
    def cases_for_contract(self, contract_id: str) -> list[ExistingCase]: ...
    def contract(self, contract_id: str) -> Contract | None: ...


def _apply_patches(records: list[dict[str, Any]], patches: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Patch records by id; a patch with an unknown id adds a new record."""
    out = copy.deepcopy(records)
    index = {r[key]: r for r in out}
    for patch in patches or []:
        if patch[key] in index:
            index[patch[key]].update(copy.deepcopy(patch))
        else:
            out.append(copy.deepcopy(patch))
            index[patch[key]] = out[-1]
    return out


class JsonERP:
    def __init__(self, data_dir: Path | str = DATA_DIR, overrides: dict[str, Any] | None = None):
        data_dir = Path(data_dir)
        erp = json.loads((data_dir / "erp_contracts.json").read_text(encoding="utf-8"))
        cases = json.loads((data_dir / "cases.json").read_text(encoding="utf-8"))
        overrides = overrides or {}
        self._properties = [Property.model_validate(p) for p in _apply_patches(erp["properties"], overrides.get("properties", []), "object_id")]
        self._contracts = [Contract.model_validate(c) for c in _apply_patches(erp["contracts"], overrides.get("contracts", []), "contract_id")]
        self._cases = [ExistingCase.model_validate(c) for c in _apply_patches(cases["cases"], overrides.get("cases", []), "case_id")]
        effective = {"p": [p.model_dump() for p in self._properties], "c": [c.model_dump() for c in self._contracts],
                     "v": [c.model_dump() for c in self._cases]}
        self.version = "sha256:" + hashlib.sha256(json.dumps(effective, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]

    def contracts(self) -> list[Contract]:
        return list(self._contracts)

    def properties(self) -> list[Property]:
        return list(self._properties)

    def contract(self, contract_id: str) -> Contract | None:
        return next((c for c in self._contracts if c.contract_id == contract_id), None)

    def cases_for_contract(self, contract_id: str) -> list[ExistingCase]:
        return [c for c in self._cases if c.contract_id == contract_id]
