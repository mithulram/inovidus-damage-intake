"""Step 4: deterministic ERP matching + status. The LLM never picks the contract."""

from __future__ import annotations

from ..context import Context
from ..matching import match as match_contracts
from ..models import CaseRecord, Flag, Gate, MessageType, Status


def run(case: CaseRecord, ctx: Context) -> CaseRecord:
    if case.understanding is None:
        raise ValueError("Schritt 'match' braucht das Ergebnis von 'understand'")
    case = case.model_copy(deep=True)
    result = match_contracts(case.understanding.extraction, case.input, ctx.erp, ctx.rules)

    if case.understanding.classification.type != MessageType.SCHADENMELDUNG:
        # Not a damage report: keep the (informational) tenant match for routing, but no action.
        route = ctx.rules.classification.out_of_scope.get(case.understanding.classification.type.value)
        target = route.route_to if route else "Kundenservice"
        result.failed_gates = [Gate.OUT_OF_SCOPE]
        result.flags = [Flag(gate=Gate.OUT_OF_SCOPE, message=f"Keine Schadenmeldung – weiterleiten an {target}")]
        result.selected_contract = None
        result.reason = f"Keine Schadenmeldung ({case.understanding.classification.type.value}) – weiterleiten an {target}."
        case.status = Status.OUT_OF_SCOPE
    elif result.failed_gates:
        case.status = Status.NEEDS_REVIEW
    else:
        case.status = Status.READY_FOR_APPROVAL
    case.match = result
    if result.unknown_sender:
        case.warnings.append("Nicht von der registrierten E-Mail-Adresse")
    return case
