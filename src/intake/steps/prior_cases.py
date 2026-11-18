"""Step 5: prior cases for the selected unit or reviewer candidates (internal only)."""

from __future__ import annotations

from ..context import Context
from ..models import CaseRecord, Gate, PriorCase
from ..normalize import fold


def run(case: CaseRecord, ctx: Context) -> CaseRecord:
    if case.match is None or case.understanding is None:
        raise ValueError("Schritt 'prior_cases' braucht Verständnis und Zuordnung")
    case = case.model_copy(deep=True)
    match = case.match
    if match.selected_contract:
        ids = [match.selected_contract]
    elif {Gate.THRESHOLD, Gate.MARGIN} & set(match.failed_gates) or not match.winner:
        ids = [c.contract_id for c in match.candidates if not c.vetoes and not c.veto_gates][:3]
    else:
        ids = [match.winner]
    category = case.understanding.classification.category
    room = case.understanding.extraction.room
    related_categories = ctx.rules.prior_cases.related_categories.get(category, [])
    case.prior_cases = []
    for contract_id in dict.fromkeys(ids):
        contract = ctx.erp.contract(contract_id)
        for old in ctx.erp.cases_for_contract(contract_id):
            if contract is None or old.unit_id != contract.unit_id:
                continue
            same_room = bool(room and old.room and fold(room) == fold(old.room))
            related_category = old.category in related_categories
            related = same_room or related_category
            reasons = ["gleiche Einheit"]
            if same_room:
                reasons.append(f"gleicher Raum ({old.room})")
            if related_category:
                reasons.append("verwandte Schadenart")
            if not related:
                reasons.append("kein erkennbarer fachlicher Zusammenhang")
            case.prior_cases.append(PriorCase(
                case_id=old.case_id, contract_id=old.contract_id, title=old.title,
                category=old.category, room=old.room, state=old.state,
                closed_at=old.closed_at, contractor=old.contractor, related=related,
                possible_duplicate=related and old.state == "open", reason=", ".join(reasons),
            ))
    return case
