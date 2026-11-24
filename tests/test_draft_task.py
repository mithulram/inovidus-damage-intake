"""Private bilingual drafts, internal tasks and staff choices."""

from datetime import datetime, timezone

import pytest

from intake.context import Context
from intake.models import Gate, InboundEmail, Status, Urgency
from intake.pipeline import process
from intake.providers.offline import OfflineProvider
from intake.steps.draft import render_reply
from intake.steps.task import run as task


@pytest.fixture
def ctx():
    return Context.build(provider=OfflineProvider(), now=lambda: datetime(2026, 11, 18, tzinfo=timezone.utc))


def damage_case(ctx, **changes):
    fields = {
        "subject": "Wasserschaden Küche", "sender_email": "max.mustermann@example.org",
        "body": "Wasser läuft in der Küche aus. Musterstr. 12, 2. OG links. Fotos vorhanden. Viele Grüße, Max Mustermann",
    }
    fields.update(changes)
    return process(InboundEmail(**fields), ctx)


@pytest.mark.parametrize("language", ["de", "en"])
@pytest.mark.parametrize("status,gates", [
    (Status.NEEDS_REVIEW, [Gate.FLOOR_MISSING, Gate.IDENTITY, Gate.VETO_ADDRESS]),
    (Status.NEEDS_REVIEW, [Gate.UNIT_AMBIGUOUS]),
    (Status.NEEDS_REVIEW, [Gate.ELIGIBILITY]),
    (Status.OUT_OF_SCOPE, [Gate.OUT_OF_SCOPE]),
])
def test_non_ready_drafts_reveal_no_erp_contracts_units_names_or_prior_cases(ctx, language, status, gates):
    case = damage_case(ctx)
    assert case.prior_cases  # Privacy assertions must exercise an actual prior case.
    case.status = status
    case.match.failed_gates = gates
    case.match.selected_contract = None
    case.understanding.extraction.language = language
    for candidate in case.match.candidates:
        candidate.tenant_name = "ERP-Geheimname Beispiel"
        candidate.unit_label = "ERP-Geheimeinheit 99"
    for variant in [None, "ask_registered_email"]:
        reply = render_reply(case, ctx, variant=variant)
        forbidden = {value for c in ctx.erp.contracts() for value in (c.contract_id, c.unit_label, c.tenant_name)}
        forbidden.update(value for c in case.match.candidates for value in (c.contract_id, c.unit_label, c.tenant_name))
        forbidden.update(value for p in case.prior_cases for value in (p.case_id, p.title, p.contractor) if value)
        assert all(value.casefold() not in reply.body.casefold() for value in forbidden)
        assert reply.auto_send is False


@pytest.mark.parametrize("language,body,standard,photo_request", [
    ("de", "Wasser läuft in der Küche aus. Musterstr. 12, 2. OG links. Fotos vorhanden. Viele Grüße, Max Mustermann",
     "24 Stunden", "Bitte senden Sie uns die Fotos"),
    ("en", "Hello, water is leaking under our kitchen sink and the cabinet is wet. We live at Musterstrasse 12, 2. OG left. Photos available. Best regards, Max Mustermann",
     "24 hours", "Please forward the photos"),
])
@pytest.mark.parametrize("attachments", [[], ["photo.jpg"]])
def test_ready_reply_metadata_deadline_photos_and_no_prior_cases(ctx, language, body, standard, photo_request, attachments):
    case = damage_case(ctx, body=body, attachments=attachments)
    assert case.status == Status.READY_FOR_APPROVAL
    reply = case.reply_draft
    assert reply.language == language
    assert reply.to == case.input.sender_email
    assert reply.subject == f"Re: {case.input.subject}"
    assert reply.variant == "standard"
    assert reply.auto_send is False
    assert standard in reply.body
    assert (photo_request in reply.body) is (not attachments)
    assert case.prior_cases
    for prior in case.prior_cases:
        for value in [prior.case_id, prior.title, prior.contractor]:
            assert value not in reply.body


@pytest.mark.parametrize("gate", [Gate.FLOOR_MISSING, Gate.FLOOR_AMBIGUOUS, Gate.UNIT_AMBIGUOUS,
                                 Gate.THRESHOLD, Gate.MARGIN, Gate.VETO_UNIT])
def test_unit_gates_ask_for_floor_and_side_with_german_counting(ctx, gate):
    case = damage_case(ctx)
    case.status = Status.NEEDS_REVIEW
    case.match.failed_gates = [gate]
    reply = render_reply(case, ctx)
    assert reply.variant == "confirm_unit"
    assert all(text in reply.body for text in ["Etage", "Wohnungsseite", "Erdgeschoss = EG", "1. OG"])


@pytest.mark.parametrize("language,expected", [
    ("de", ["vollständige Anschrift", "Etage", "Wohnungsseite"]),
    ("en", ["full address", "floor", "apartment side"]),
])
@pytest.mark.parametrize("building_uncertain", [True, False])
def test_unit_ambiguity_requests_exact_location_without_erp_facts(ctx, language, expected, building_uncertain):
    case = damage_case(ctx, body="Wasser läuft aus. Musterstr. 12, 2. OG links oder 3. OG rechts. "
                               "Viele Grüße, Max Mustermann")
    assert case.match.failed_gates == [Gate.UNIT_AMBIGUOUS]
    case.match.building_uncertain = building_uncertain
    case.understanding.extraction.language = language
    reply = render_reply(case, ctx)
    variants = {"confirm_unit", "confirm_address"} if building_uncertain else {"confirm_unit"}
    assert set(reply.variant.split("+")) == variants
    assert all(text in reply.body for text in expected)
    forbidden = {value for c in ctx.erp.contracts()
                 for value in (c.contract_id, c.unit_label, c.tenant_name, c.unit_id, c.object_id)}
    assert all(value not in reply.body for value in forbidden)
    assert reply.auto_send is False


@pytest.mark.parametrize("language,address_request", [("de", "vollständige Anschrift"), ("en", "full address")])
def test_building_uncertainty_requests_address_without_address_gate(ctx, language, address_request):
    case = damage_case(ctx)
    case.status = Status.NEEDS_REVIEW
    case.match.failed_gates = [Gate.ELIGIBILITY]
    case.match.building_uncertain = True
    case.understanding.extraction.language = language
    reply = render_reply(case, ctx)
    assert "confirm_address" in reply.variant
    assert address_request in reply.body


def test_failed_gates_combine_questions_and_eligibility_stays_neutral(ctx):
    case = damage_case(ctx)
    case.status = Status.NEEDS_REVIEW
    case.match.failed_gates = [Gate.FLOOR_MISSING, Gate.IDENTITY, Gate.VETO_ADDRESS]
    reply = render_reply(case, ctx)
    assert set(reply.variant.split("+")) == {"confirm_unit", "confirm_identity", "confirm_address"}
    assert all(text in reply.body for text in ["Etage", "Vertragsinhabers", "Anschrift"])
    case.match.failed_gates = [Gate.ELIGIBILITY]
    reply = render_reply(case, ctx)
    assert "Wir prüfen Ihre Angaben und melden uns" in reply.body
    assert all(word not in reply.body.lower() for word in ["inaktiv", "beendet", "leerstand"])


def test_registered_email_variant_requests_resubmission_without_disclosing_address(ctx):
    case = damage_case(ctx)
    reply = render_reply(case, ctx, variant="ask_registered_email")
    assert "erneut" in reply.body and "registriert" in reply.body
    assert "max.mustermann@example.org" not in reply.body
    with pytest.raises(ValueError):
        render_reply(case, ctx, variant="send")


@pytest.mark.parametrize("known_building", [True, False])
def test_review_emergency_is_object_scope_only_with_known_building_and_safety_precedes_promise(ctx, known_building):
    case = damage_case(ctx, subject="Gasgeruch", body="Gasgeruch in Musterstraße 12. Max Mustermann")
    assert case.status == Status.NEEDS_REVIEW
    assert case.urgency.level == Urgency.NOTFALL
    assert case.match.object_id == "OBJ-MS12"
    if not known_building:
        case.match.object_id = None
    result = task(case, ctx)
    internal = result.internal_task
    assert internal.scope == ("object" if known_building else "clarification")
    assert internal.contract_id is None
    assert internal.object_id == ("OBJ-MS12" if known_building else None)
    assert internal.priority == Urgency.NOTFALL
    assert internal.due_hours == 2
    assert internal.requires_approval is True
    if known_building:
        assert "Musterstraße 12" in internal.title
        assert "OBJ-MS12" not in internal.title
        assert any("Notdienst" in item and "Gebäude" in item for item in internal.checklist)
        assert any("Hausmeister" in item for item in internal.checklist)
    reply = render_reply(result, ctx)
    assert "Etage" in reply.body and "Wohnungsseite" in reply.body
    promise = reply.body.index("Wir kümmern uns umgehend")
    positions = [reply.body.index(instruction) for instruction in case.urgency.safety_instructions]
    assert positions and positions == sorted(positions)
    assert all(position < promise for position in positions)
    assert "Max Mustermann" not in reply.body and "MV-" not in reply.body


def test_clarification_title_uses_address_and_keeps_object_id(ctx):
    case = damage_case(ctx, body="Wasser läuft in Musterstraße 12. Max Mustermann")
    assert case.internal_task.scope == "clarification"
    assert "Musterstraße 12" in case.internal_task.title
    assert "OBJ-MS12" not in case.internal_task.title
    assert case.internal_task.object_id == "OBJ-MS12"


def test_contract_task_contains_deadline_photos_caretaker_and_related_history(ctx):
    case = damage_case(ctx)
    internal = case.internal_task
    assert internal.scope == "contract"
    assert internal.contract_id == "MV-10245"
    assert internal.object_id == "OBJ-MS12"
    assert all(text in internal.title for text in ["Sanitär", "Wasserschaden", "Küche", "MV-10245"])
    assert internal.assignee_role == "Technik / Sanitär"
    assert internal.priority == Urgency.DRINGEND
    assert internal.due_hours == 24
    assert internal.requires_approval is True
    assert any("24 Stunden" in item for item in internal.checklist)
    assert any("Fotos" in item for item in internal.checklist)
    assert any("Hausmeister" in item for item in internal.checklist)
    related = [p for p in case.prior_cases if p.related]
    assert internal.related_cases == [p.case_id for p in related]
    for prior in related:
        assert any(all(text in item for text in [prior.case_id, prior.title, prior.contractor, "Gewährleistung"])
                   for item in internal.checklist)


def test_ready_emergency_task_requests_immediate_emergency_service(ctx):
    case = damage_case(ctx, subject="Rohrbruch")
    assert case.status == Status.READY_FOR_APPROVAL
    assert case.internal_task.scope == "contract"
    assert case.internal_task.priority == Urgency.NOTFALL
    assert case.internal_task.due_hours == 2
    assert "Notdienst sofort beauftragen" in case.internal_task.checklist


@pytest.mark.parametrize("level", list(Urgency))
def test_contractor_checklist_uses_natural_response_target_without_duplicate_deadline(ctx, level):
    case = damage_case(ctx)
    target = ctx.rules.urgency.levels[level]
    case.urgency.level = level
    case.urgency.response_target = target.response_target
    case.urgency.due_hours = target.due_hours
    result = task(case, ctx)
    booking, = [item for item in result.internal_task.checklist if item.startswith("Handwerker beauftragen")]
    assert booking == f"Handwerker beauftragen – Ziel: {target.response_target}"


@pytest.mark.parametrize("level,target", [(Urgency.DRINGEND, "a contractor within 24 hours"),
                                         (Urgency.NORMAL, "within 5 working days")])
def test_english_standard_reply_has_natural_response_target(ctx, level, target):
    case = damage_case(ctx)
    case.understanding.extraction.language = "en"
    case.urgency.level = level
    case.urgency.response_target = ctx.rules.urgency.levels[level].response_target
    assert f"Our response or service target: {target}." in render_reply(case, ctx).body


def test_task_lists_every_related_prior_case_and_excludes_unrelated_history():
    ctx = Context.build(provider=OfflineProvider(), now=lambda: datetime(2026, 11, 18, tzinfo=timezone.utc),
                        data_overrides={"cases": [
                            {"case_id": "SECOND-RELATED", "contract_id": "MV-10245", "unit_id": "OBJ-MS12-2L",
                             "title": "Früherer Rohrbruch", "category": "Rohrbruch", "room": "Bad", "state": "open",
                             "contractor": "Weiterer Sanitärbetrieb"},
                            {"case_id": "UNRELATED", "contract_id": "MV-10245", "unit_id": "OBJ-MS12-2L",
                             "title": "Steckdose Schlafzimmer", "category": "Elektrik", "room": "Schlafzimmer", "state": "closed"},
                        ]})
    case = damage_case(ctx)
    assert len(case.prior_cases) == 3
    assert set(case.internal_task.related_cases) == {"VG-2026-0412", "SECOND-RELATED"}
    checklist = "\n".join(case.internal_task.checklist)
    for prior in case.prior_cases:
        assert (prior.case_id in checklist) is prior.related
        assert (prior.title in checklist) is prior.related
        assert prior.case_id not in case.reply_draft.body
        assert prior.title not in case.reply_draft.body


def test_out_of_scope_routes_with_normal_priority_and_no_damage_promise(ctx):
    case = damage_case(ctx, subject="Mieterhöhung", body="Frage zur Miete. Viele Grüße, Max Mustermann")
    assert case.status == Status.OUT_OF_SCOPE
    assert case.internal_task.scope == "routing"
    assert case.internal_task.assignee_role == "Mietbuchhaltung"
    assert case.internal_task.priority == Urgency.NORMAL
    assert case.internal_task.contract_id is None
    assert "Mietbuchhaltung" in case.reply_draft.body
    assert "Schadenmeldung" not in case.reply_draft.body
    assert "Handwerker" not in case.reply_draft.body


@pytest.mark.parametrize("erp_email", [None, "max.mustermann@example.org"])
@pytest.mark.parametrize("erp_phone,email_phone", [(None, None), ("+49 30 1234 5601", None), (None, "+49 30 9999 5678"), ("+49 30 1234 5601", "+49 30 9999 5678")])
def test_staff_options_availability_and_phone_details(ctx, erp_email, erp_phone, email_phone):
    case = damage_case(ctx, sender_email="unregistered@example.net")
    assert case.match.unknown_sender is True
    ctx.erp.contract(case.match.winner).contact.email = erp_email
    ctx.erp.contract(case.match.winner).contact.phone = erp_phone
    case.understanding.extraction.phone = email_phone
    options = {option.code: option for option in task(case, ctx).staff_options}
    assert set(options) == {"reply_anyway", "ask_registered_email", "call_tenant"}
    assert options["reply_anyway"].available is True
    assert options["ask_registered_email"].available is bool(erp_email)
    assert options["call_tenant"].available is bool(erp_phone or email_phone)
    assert options["call_tenant"].detail == (erp_phone or email_phone)
    assert all(option.label for option in options.values())


def test_staff_options_absent_for_registered_sender(ctx):
    case = damage_case(ctx)
    assert case.match.unknown_sender is False
    assert case.staff_options == []
