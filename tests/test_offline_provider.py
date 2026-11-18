"""WO1: rule-based classification and raw extraction, without a live provider."""

import socket

import pytest

from intake.context import Context
from intake.models import Gate, InboundEmail, MessageType, Status, Urgency
from intake.normalize import normalize_floor, normalize_side
from intake.pipeline import process
from intake.providers.offline import OfflineProvider
from intake.rules import ROOT, load_rules
from intake.scenarios import FIXED_NOW, load_scenario, run_scenario
from intake.steps.draft import load_templates


@pytest.fixture
def rules():
    return load_rules()


@pytest.mark.parametrize("subject,body,kind,category,trade,confidence,keyword", [
    ("WASSER", "Frage zur Miete", MessageType.SCHADENMELDUNG, "Wasserschaden", "Sanitär", 0.9, "wasser"),
    ("Mieterhöhung", "Bitte erläutern", MessageType.ANFRAGE_MIETE, None, None, 0.6, "mieterhöhung"),
    ("Hallo", "Vielen Dank", MessageType.SONSTIGES, None, None, 0.6, "keine"),
    ("Schaden", "Gasgeruch und Wasser", MessageType.SCHADENMELDUNG, "Gasgeruch", "Gas / Heizung", 0.9, "gasgeruch"),
])
def test_classification_damage_precedes_routing_and_categories_follow_priority(
    rules, subject, body, kind, category, trade, confidence, keyword,
):
    result = OfflineProvider().understand(InboundEmail(subject=subject, body=body), rules)
    assert result.classification.type == kind
    assert result.classification.category == category
    assert result.classification.trade == trade
    assert result.classification.confidence == confidence
    assert keyword in result.classification.reason.lower()
    assert "Schlüsselwörter" in result.classification.reason
    assert result.provider == "offline"
    assert result.model is None
    assert result.urgency_hint is None


def test_classifier_uses_configured_keywords_and_category_order():
    rules = load_rules(overrides={"classification": {
        "damage_keywords": ["prüfwort"],
        "categories": [
            {"name": "Erste Kategorie", "trade": "Erstes Gewerk", "keywords": ["prüfwort"]},
            {"name": "Zweite Kategorie", "trade": "Zweites Gewerk", "keywords": ["prüfwort"]},
        ],
    }})
    result = OfflineProvider().understand(InboundEmail(body="PRÜFWORT"), rules)
    assert result.classification.type == MessageType.SCHADENMELDUNG
    assert result.classification.category == "Erste Kategorie"
    assert result.classification.trade == "Erstes Gewerk"


@pytest.mark.parametrize("street,number", [
    ("Musterstr", "12"), ("Musterstr.", "12"), ("Musterstraße", "16"), ("Musterstrasse", "12"),
    ("Beispielweg", "7a"), ("Testplatz", "3"), ("Testallee", "4"),
    ("Testgasse", "5"), ("Testring", "6"),
])
@pytest.mark.parametrize("separator", [" ", ""])
def test_address_is_copied_as_written(rules, street, number, separator):
    result = OfflineProvider().understand(InboundEmail(body=f"Wasser bei {street}{separator}{number}, 2. OG links."), rules)
    assert result.extraction.street_raw == street
    assert result.extraction.house_no == number


@pytest.mark.parametrize("phrase,floor,status", [
    ("zweite Etage", 2, "ok"), ("2. OG", 2, "ok"), ("2. Etage", 2, "ok"),
    ("3. OG", 3, "ok"), ("EG", 0, "ok"), ("2nd floor", 2, "english_ordinal"),
    ("Hochparterre", None, "unclear"), ("im dritten Stock", 3, "ok"),
])
def test_raw_floor_phrase_parses_with_shared_normalizer(rules, phrase, floor, status):
    result = OfflineProvider().understand(InboundEmail(body=f"Musterstr. 12, {phrase} links. Wasser tropft."), rules)
    assert result.extraction.floor_raw == phrase
    assert normalize_floor(result.extraction.floor_raw, rules.normalize)[:2] == (floor, status)


@pytest.mark.parametrize("phrase,side", [
    ("links", "L"), ("li.", "L"), ("rechts", "R"), ("re.", "R"),
    ("left", "L"), ("right", "R"), ("Mitte", "M"),
])
def test_raw_side_phrase_parses_with_shared_normalizer(rules, phrase, side):
    result = OfflineProvider().understand(InboundEmail(body=f"Musterstr. 12, 2. OG {phrase} Wasser."), rules)
    assert result.extraction.side_raw == phrase
    assert normalize_side(result.extraction.side_raw, rules.normalize) == side


@pytest.mark.parametrize("closing", ["Viele Grüße,", "Grüße", "LG", "Best regards,", "Regards,", ""])
def test_signature_is_sender_and_default_contract_holder(rules, closing):
    result = OfflineProvider().understand(InboundEmail(body=f"Wasser tropft. {closing} Max Mustermann"), rules)
    assert result.extraction.sender_name == "Max Mustermann"
    assert result.extraction.tenant_name == "Max Mustermann"


@pytest.mark.parametrize("holder_phrase", ["Wohnung von", "für meinen Partner"])
def test_explicit_holder_is_distinct_from_sender(rules, holder_phrase):
    result = OfflineProvider().understand(InboundEmail(
        body=f"{holder_phrase} Max Mustermann, Musterstr. 12, 2. OG links. Wasser tropft. Viele Grüße, Erika Muster",
    ), rules)
    assert result.extraction.tenant_name == "Max Mustermann"
    assert result.extraction.sender_name == "Erika Muster"


@pytest.mark.parametrize("since,language,sentence", [
    ("Seit gestern", "de", "Seit gestern läuft Wasser in der Küche aus."),
    ("seit heute Morgen", "de", "Bei uns läuft seit heute Morgen Wasser in der Küche aus."),
    ("since yesterday", "en", "Hello, since yesterday water is leaking under our kitchen sink and the cabinet is wet."),
])
def test_damage_details_are_raw_and_language_is_detected(rules, since, language, sentence):
    result = OfflineProvider().understand(InboundEmail(
        body=f"{sentence} Fotos/photo vorhanden. Telefon +49 30 1234 5678. Viele Grüße, Max Mustermann",
    ), rules)
    extraction = result.extraction
    assert extraction.damage_description == sentence
    assert extraction.since == since
    assert extraction.room == ("kitchen" if language == "en" else "Küche")
    assert extraction.photos_mentioned is True
    assert extraction.phone == "+49 30 1234 5678"
    assert extraction.language == language


def test_absent_details_are_not_invented_and_provider_is_offline(rules, monkeypatch):
    def forbid_network(*args, **kwargs):
        pytest.fail("The offline provider must not open a network connection")

    monkeypatch.setattr(socket, "socket", forbid_network)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    provider = OfflineProvider()
    email = InboundEmail(body="Hallo, danke.")
    result = provider.understand(email, rules)
    assert result == provider.understand(email, rules)
    assert result.extraction.model_dump() == {
        "tenant_name": None, "sender_name": None, "street_raw": None, "house_no": None,
        "floor_raw": None, "side_raw": None, "room": None, "damage_description": None,
        "since": None, "photos_mentioned": False, "phone": None, "language": "de", "location_alternatives": [],
    }


@pytest.mark.parametrize("keyword", [
    word for rule in load_rules().urgency.rules if rule.level == Urgency.NOTFALL for word in rule.any
])
def test_every_emergency_phrase_stays_in_scope_and_urgent_end_to_end(keyword):
    ctx = Context.build(provider=OfflineProvider(), now=lambda: FIXED_NOW)
    case = process(InboundEmail(body=f"{keyword}. Musterstr. 12, 2. OG links. Max Mustermann"), ctx)
    assert case.understanding.classification.type == MessageType.SCHADENMELDUNG
    assert case.status == Status.READY_FOR_APPROVAL
    assert case.urgency.level == Urgency.NOTFALL
    assert case.internal_task.priority == Urgency.NOTFALL
    assert case.internal_task.scope == "contract"
    assert case.reply_draft.variant == "NOTFALL"
    translations = load_templates()["translations"]
    for instruction in case.urgency.safety_instructions:
        translated = translations.get(case.reply_draft.language, {}).get(instruction, instruction)
        assert translated in case.reply_draft.body


@pytest.mark.parametrize("source", ["category", "urgency"])
def test_damage_routing_includes_configured_category_and_urgency_keywords(source):
    overrides = {"classification": {"damage_keywords": [], "categories": []}}
    if source == "category":
        overrides["classification"]["categories"] = [
            {"name": "Testschaden", "trade": "Testgewerk", "keywords": ["prüfwort"]},
        ]
    else:
        overrides["urgency"] = {"rules": [{"level": "DRINGEND", "label": "Testregel", "any": ["prüfwort"]}]}
    rules = load_rules(overrides=overrides)
    result = OfflineProvider().understand(InboundEmail(body="PRÜFWORT. Frage zur Miete."), rules)
    assert result.classification.type == MessageType.SCHADENMELDUNG
    assert "prüfwort" in result.classification.reason


@pytest.mark.parametrize("location,extra", [
    ("2. OG links oder 3. OG rechts", "3. OG rechts"),
    ("2. OG links und 3. OG links", "3. OG links"),
    ("2. OG links und 2. OG rechts", "rechts"),
    ("2. OG links und rechts", "rechts"),
    ("2. OG links. Außerdem Musterstr. 16, 2. OG links", "Musterstr. 16"),
    ("2. OG links. Außerdem Beispielweg 7a, 2. OG links", "Beispielweg 7a"),
])
def test_distinct_locations_keep_first_floor_and_side_and_copy_extra_span(rules, location, extra):
    email = InboundEmail(body=f"Wasser läuft aus. Musterstr. 12, {location}. Max Mustermann")
    result = OfflineProvider().understand(email, rules)
    assert result.extraction.floor_raw == "2. OG"
    assert result.extraction.side_raw == "links"
    assert extra in result.extraction.location_alternatives
    assert all(span in email.body for span in result.extraction.location_alternatives)
    case = process(email, Context.build(provider=OfflineProvider(), now=lambda: FIXED_NOW))
    assert case.status == Status.NEEDS_REVIEW
    assert Gate.UNIT_AMBIGUOUS in case.match.failed_gates
    assert case.match.selected_contract is None


@pytest.mark.parametrize("marker", ["unsicher", "weiß nicht genau", "weiss nicht genau", "glaube", "vielleicht",
                                    "not sure", "maybe", "I think"])
@pytest.mark.parametrize("before", [True, False])
def test_uncertainty_near_location_is_literal_evidence(rules, marker, before):
    location = f"{marker}: 2. OG links" if before else f"2. OG links; {marker}"
    email = InboundEmail(body=f"Wasser läuft aus. Musterstr. 12, {location}. Max Mustermann")
    extraction = OfflineProvider().understand(email, rules).extraction
    assert extraction.floor_raw == "2. OG" and extraction.side_raw == "links"
    assert extraction.location_alternatives == [marker]


@pytest.mark.parametrize("body", [
    "Wasser läuft aus. Musterstr. 12, 2. OG links. Bitte kommen Sie heute oder morgen. Max Mustermann",
    "Das Bad oder die Küche? Egal, Wasser läuft in der Küche aus. Musterstr. 12, 2. OG links. Max Mustermann",
    "Water is leaking. Musterstr. 12, 2. OG left. Please come either today or tomorrow. Max Mustermann",
    "Wasser läuft aus. Musterstr. 12, 2. OG links; bitte heute oder morgen kommen. Max Mustermann",
    "Water is leaking. Musterstr. 12, 2. OG left; please come either today or tomorrow. Max Mustermann",
])
def test_unrelated_alternatives_do_not_force_location_review(rules, body):
    email = InboundEmail(body=body)
    extraction = OfflineProvider().understand(email, rules).extraction
    assert extraction.location_alternatives == []
    case = process(email, Context.build(provider=OfflineProvider(), now=lambda: FIXED_NOW))
    assert case.status == Status.READY_FOR_APPROVAL
    assert Gate.UNIT_AMBIGUOUS not in case.match.failed_gates


@pytest.mark.parametrize("marker", ["unsicher", "weiß nicht genau", "glaube", "vielleicht",
                                    "not sure", "maybe", "I think"])
@pytest.mark.parametrize("punctuation", [".", "?", "!"])
@pytest.mark.parametrize("before", [True, False])
def test_uncertainty_in_a_different_sentence_does_not_apply_to_location(rules, marker, punctuation, before):
    location = "Musterstr. 12, 2. OG links"
    body = f"{marker}{punctuation} {location}." if before else f"{location}{punctuation} {marker}."
    extraction = OfflineProvider().understand(InboundEmail(body=body), rules).extraction
    assert extraction.location_alternatives == []


@pytest.mark.parametrize("body", [
    "Ich bin unsicher: Musterstr. 12, 2. OG links.",
    "Musterstr. 12, 2. OG links; ich bin unsicher.",
    "Musterstr. 12, 2. OG li.; ich bin unsicher.",
])
def test_location_abbreviations_and_ordinals_are_not_sentence_boundaries(rules, body):
    extraction = OfflineProvider().understand(InboundEmail(body=body), rules).extraction
    assert extraction.location_alternatives == ["unsicher"]


def test_inspection_example_forces_unit_review():
    email = InboundEmail(body="Wasser läuft aus. Musterstr. 12, 2. OG links oder 3. OG rechts; "
                         "ich bin bei der Etage unsicher. Viele Grüße, Max Mustermann")
    case = process(email, Context.build(provider=OfflineProvider(), now=lambda: FIXED_NOW))
    assert case.status == Status.NEEDS_REVIEW
    assert Gate.UNIT_AMBIGUOUS in case.match.failed_gates
    assert case.match.selected_contract is None
    assert case.understanding.extraction.floor_raw == "2. OG"
    assert case.understanding.extraction.side_raw == "links"
    assert case.understanding.extraction.location_alternatives == ["3. OG rechts", "ich bin bei der Etage unsicher"]


@pytest.mark.parametrize("body,subject", [
    ("Musterstr. 12, 2. OG links. Musterstraße 12, zweite Etage left.", "Musterstrasse 12, 2. OG links"),
    ("Musterstr. 12, EG links. Musterstraße 12, Erdgeschoss left.", ""),
    ("Musterstr. 12, 2. OG links.", "oder unsicher"),
    ("Ich bin unsicher, ob ich Fotos senden soll. " + "Hier sind weitere Informationen. " * 4
     + "Musterstr. 12, 2. OG links.", ""),
])
def test_repeated_equivalent_locations_and_distant_uncertainty_are_not_alternatives(rules, body, subject):
    result = OfflineProvider().understand(InboundEmail(subject=subject, body=body), rules)
    assert result.extraction.location_alternatives == []


@pytest.mark.parametrize("filename,status", [("S01_original.yaml", Status.READY_FOR_APPROVAL),
                                           ("S06_rent_question.yaml", Status.OUT_OF_SCOPE)])
def test_original_and_rent_scenarios_are_preserved(filename, status):
    scenario_path = ROOT / "scenarios" / filename
    case, checks = run_scenario(load_scenario(scenario_path), provider=OfflineProvider())
    assert all(c.passed for c in checks)
    assert case.status == status
    assert case.understanding.extraction.location_alternatives == []


@pytest.mark.parametrize("room,expected", [("Küche", "Küche"), ("KÜCHE", "KÜCHE"), ("küche", "küche"),
                                          ("Kitchen", "Kitchen"), ("Kueche", "Küche")])
def test_room_preserves_original_casing_with_capitalized_fallback(rules, room, expected):
    result = OfflineProvider().understand(InboundEmail(body=f"Wasser in der {room}."), rules)
    assert result.extraction.room == expected


def test_multiline_location_uncertainty_still_forces_review():
    email = InboundEmail(body="Wasser läuft aus. Musterstr. 12,\n2. OG\nlinks;\n"
                         "Bei der Etage bin ich unsicher. Viele Grüße, Max Mustermann")
    case = process(email, Context.build(provider=OfflineProvider(), now=lambda: FIXED_NOW))
    assert case.understanding.extraction.floor_raw == "2. OG"
    assert case.understanding.extraction.side_raw == "links"
    assert case.status == Status.NEEDS_REVIEW
    assert Gate.UNIT_AMBIGUOUS in case.match.failed_gates


@pytest.mark.parametrize("body_address,subject_address", [
    ("Musterstr 14", "Musterstraße 12"),
    ("Musterstraße12", "Musterstr.14"),
    ("Beispielweg7a", "Musterstrasse 12"),
])
def test_body_address_wins_and_conflicting_subject_forces_review(rules, body_address, subject_address):
    email = InboundEmail(
        subject=f"Wasserschaden Küche, {subject_address}",
        body=f"Wasser läuft aus. {body_address}, zweite Etage links. Viele Grüße, Max Mustermann",
        sender_email="max.mustermann@example.org",
    )
    extraction = OfflineProvider().understand(email, rules).extraction
    assert extraction.street_raw + extraction.house_no == body_address.replace(" ", "")
    assert extraction.location_alternatives == [subject_address]
    case = process(email, Context.build(provider=OfflineProvider(), now=lambda: FIXED_NOW))
    assert case.status == Status.NEEDS_REVIEW
    assert case.match.selected_contract is None
    assert Gate.UNIT_AMBIGUOUS in case.match.failed_gates
    assert case.match.building_uncertain is True


def test_bare_and_compact_equivalent_addresses_do_not_force_review(rules):
    email = InboundEmail(subject="Musterstraße12", body="Musterstr 12, 2. OG links.")
    extraction = OfflineProvider().understand(email, rules).extraction
    assert extraction.street_raw == "Musterstr"
    assert extraction.house_no == "12"
    assert extraction.location_alternatives == []


@pytest.mark.parametrize("sentence,building_uncertain", [
    ("Bei der Etage bin ich unsicher", False),
    ("Die Hausnummer weiß ich nicht genau", True),
    ("Die Hausnummer weiss ich nicht genau", True),
    ("not sure about the floor", False),
    ("I am not sure about the address", True),
])
@pytest.mark.parametrize("before", [True, False])
def test_separate_sentence_referring_to_location_forces_review(sentence, building_uncertain, before):
    location = "Musterstr. 12, 2. OG links."
    body = f"{sentence}. {location}" if before else f"{location} {sentence}."
    email = InboundEmail(body=f"Wasser läuft aus. {body} Viele Grüße, Max Mustermann",
                         sender_email="max.mustermann@example.org")
    case = process(email, Context.build(provider=OfflineProvider(), now=lambda: FIXED_NOW))
    assert case.understanding.extraction.location_alternatives == [sentence]
    assert sentence in email.body
    assert case.status == Status.NEEDS_REVIEW
    assert Gate.UNIT_AMBIGUOUS in case.match.failed_gates
    assert case.match.selected_contract is None
    assert case.match.building_uncertain is building_uncertain


@pytest.mark.parametrize("sentence", [
    "Ich bin unsicher, ob die Versicherung zahlt",
    "Die Deckung weiß ich nicht genau",
    "not sure whether insurance pays",
])
@pytest.mark.parametrize("before", [True, False])
def test_separate_sentence_with_unrelated_uncertainty_does_not_force_review(sentence, before):
    location = "Musterstr. 12, 2. OG links."
    body = f"{sentence}. {location}" if before else f"{location} {sentence}."
    case = process(InboundEmail(body=f"Wasser läuft aus. {body} Viele Grüße, Max Mustermann"),
                   Context.build(provider=OfflineProvider(), now=lambda: FIXED_NOW))
    assert case.understanding.extraction.location_alternatives == []
    assert case.status == Status.READY_FOR_APPROVAL


def test_kaltmiete_question_is_routed_to_rent_accounting():
    case = process(InboundEmail(
        subject="Frage zur Kaltmiete",
        body="Frage zur Kaltmiete. Musterstr. 12, 2. OG links. Viele Grüße, Max Mustermann",
        sender_email="max.mustermann@example.org",
    ), Context.build(provider=OfflineProvider(), now=lambda: FIXED_NOW))
    assert case.understanding.classification.type == MessageType.ANFRAGE_MIETE
    assert case.understanding.classification.category is None
    assert case.status == Status.OUT_OF_SCOPE
    assert case.internal_task.scope == "routing"
    assert case.internal_task.assignee_role == "Mietbuchhaltung"


@pytest.mark.parametrize("keyword,compound", [("kalt", "Kaltmiete"), ("sink", "sinking"),
                                             ("door", "outdoor"), ("power", "powerbank"),
                                             ("schloss", "abgeschlossen")])
def test_category_terms_match_words_but_not_substrings(rules, keyword, compound):
    provider = OfflineProvider()
    result = provider.understand(InboundEmail(body=compound), rules)
    assert result.classification.type != MessageType.SCHADENMELDUNG
    assert result.classification.category is None
    result = provider.understand(InboundEmail(body=f"({keyword.upper()})!"), rules)
    assert result.classification.type == MessageType.SCHADENMELDUNG
    assert result.classification.category is not None


@pytest.mark.parametrize("keyword,category", [("Wasserschaden", "Wasserschaden"),
                                             ("Heizungsausfall", "Heizungsausfall"),
                                             ("Stromausfall", "Elektrik"),
                                             ("verstopft", "Rohrverstopfung"),
                                             ("Verstopfung", "Rohrverstopfung"),
                                             ("Rohrverstopfung", "Rohrverstopfung")])
def test_configured_compounds_and_inflections_keep_their_category(rules, keyword, category):
    result = OfflineProvider().understand(InboundEmail(body=keyword), rules)
    assert result.classification.type == MessageType.SCHADENMELDUNG
    assert result.classification.category == category


@pytest.mark.parametrize("sentence", ["Ich bin unsicher, ob die Versicherung zahlt",
                                      "not sure whether insurance pays"])
def test_unrelated_uncertainty_after_location_in_same_sentence_is_not_an_alternative(rules, sentence):
    email = InboundEmail(body=f"Musterstr. 12, 2. OG links; {sentence}.")
    assert OfflineProvider().understand(email, rules).extraction.location_alternatives == []


def test_uncertainty_question_about_location_still_forces_review(rules):
    email = InboundEmail(body="Ich bin unsicher, ob es die zweite Etage links ist. Musterstr. 12.")
    assert OfflineProvider().understand(email, rules).extraction.location_alternatives == [
        "Ich bin unsicher, ob es die zweite Etage links ist",
    ]


@pytest.mark.parametrize("location,alternatives,building_uncertain", [
    ("Musterstraße 12 oder 14, 2. OG links", ["14"], True),
    ("Musterstr. 12/14, 2. OG links", ["14"], True),
    ("Musterstr. 12, 2. oder 3. OG links", ["2.", "3. OG"], False),
    ("Musterstr. 12, 2. oder 3. Etage links", ["2.", "3. Etage"], False),
    ("Musterstr. 12, 2. OG links oder rechts", ["rechts"], False),
])
@pytest.mark.parametrize("in_subject", [False, True])
def test_shared_location_choices_force_review_and_preserve_literal_spans(
    location, alternatives, building_uncertain, in_subject,
):
    email = InboundEmail(
        subject=location if in_subject else "",
        body="Gasgeruch. " + ("" if in_subject else location + ". ") + "Viele Grüße, Max Mustermann",
    )
    case = process(email, Context.build(provider=OfflineProvider(), now=lambda: FIXED_NOW))
    assert case.understanding.extraction.location_alternatives == alternatives
    assert all(span in location for span in alternatives)
    assert case.status == Status.NEEDS_REVIEW
    assert Gate.UNIT_AMBIGUOUS in case.match.failed_gates
    assert case.match.selected_contract is None
    assert case.match.building_uncertain is building_uncertain
    if building_uncertain:
        assert case.match.object_id is None
        assert case.internal_task.scope == "clarification"


@pytest.mark.parametrize("clause", [
    "bei der Hausnummer bin ich unsicher",
    "Bei der Etage bin ich unsicher",
    "ich bin mir bei der Adresse unsicher",
])
@pytest.mark.parametrize("separator", ["; ", ". ", ";\n"])
def test_nearby_location_does_not_truncate_referring_clause(clause, separator):
    email = InboundEmail(body=f"Gasgeruch. Musterstr. 12, 2. OG links{separator}"
                         f"{clause}. Viele Grüße, Max Mustermann")
    case = process(email, Context.build(provider=OfflineProvider(), now=lambda: FIXED_NOW))
    assert case.understanding.extraction.location_alternatives == [clause]
    assert case.match.selected_contract is None
    assert case.status == Status.NEEDS_REVIEW
    if "Etage" not in clause:
        assert case.match.building_uncertain is True
        assert case.match.object_id is None
        assert case.internal_task.scope != "object"
