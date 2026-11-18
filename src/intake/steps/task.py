"""Step 9: reviewable internal task and staff choices; no external effects."""

from __future__ import annotations

from ..context import Context
from ..models import CaseRecord, InternalTask, StaffOption, Status, Urgency
from .draft import load_templates, route_to


def run(case: CaseRecord, ctx: Context) -> CaseRecord:
    if case.match is None or case.understanding is None or case.urgency is None or case.status is None:
        raise ValueError("Aufgabe braucht Verständnis, Zuordnung, Status und Dringlichkeit")
    case = case.model_copy(deep=True)
    templates = load_templates()
    t = templates["task"]
    match, urgency = case.match, case.urgency
    related = [p for p in case.prior_cases if p.related]
    if case.status == Status.OUT_OF_SCOPE:
        target = route_to(case, ctx)
        task = InternalTask(
            title=t["routing_title"].format(route_to=target), scope="routing", assignee_role=target,
            priority=Urgency.NORMAL, due_hours=ctx.rules.urgency.levels[Urgency.NORMAL].due_hours,
            checklist=[t["routing_checklist"].format(route_to=target)],
        )
    elif case.status == Status.READY_FOR_APPROVAL:
        contract = ctx.erp.contract(match.selected_contract) if match.selected_contract else None
        if contract is None:
            raise ValueError("Eindeutige Zuordnung braucht einen vorhandenen ERP-Vertrag")
        category = case.understanding.classification.category or t["default_category"]
        trade = case.understanding.classification.trade or t["default_trade"]
        room = case.understanding.extraction.room or ""
        checklist = [t["book_contractor"].format(response_target=urgency.response_target, due_hours=urgency.due_hours)]
        if urgency.level == Urgency.NOTFALL:
            checklist.insert(0, t["emergency"])
        if case.understanding.extraction.photos_mentioned:
            checklist.append(t["photos"])
        checklist.append(t["caretaker"])
        checklist.extend(t["prior_case"].format(title=p.title, case_id=p.case_id,
                                              contractor=p.contractor or t["unknown_contractor"]) for p in related)
        task = InternalTask(
            title=t["contract_title"].format(trade=trade, category=category, room=room,
                                             contract_id=contract.contract_id),
            scope="contract", assignee_role=t["contract_assignee"].format(trade=trade),
            priority=urgency.level, due_hours=urgency.due_hours,
            contract_id=contract.contract_id, object_id=contract.object_id, checklist=checklist,
            related_cases=[p.case_id for p in related],
        )
    else:
        gates = "; ".join(f.message for f in match.flags) or t["default_gate"]
        object_scope = urgency.level == Urgency.NOTFALL and bool(match.object_id)
        prefix = "object" if object_scope else "clarification"
        task = InternalTask(
            title=t[prefix + "_title"].format(gates=gates, object_id=match.object_id),
            scope=prefix, assignee_role=t[prefix + "_assignee"],
            priority=urgency.level, due_hours=urgency.due_hours,
            object_id=match.object_id if object_scope else None, checklist=list(t[prefix]),
            related_cases=[p.case_id for p in related],
        )
    case.internal_task = task
    case.staff_options = []
    if match.unknown_sender:
        winner = ctx.erp.contract(match.winner) if match.winner else None
        phone = (winner.contact.phone if winner else None) or case.understanding.extraction.phone
        labels = templates["staff_options"]
        case.staff_options = [
            StaffOption(code="reply_anyway", label=labels["reply_anyway"], available=True),
            StaffOption(code="ask_registered_email", label=labels["ask_registered_email"],
                        available=bool(winner and winner.contact.email)),
            StaffOption(code="call_tenant", label=labels["call_tenant"], available=bool(phone), detail=phone),
        ]
    return case
