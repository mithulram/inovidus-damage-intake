"""Own probe review (Claude, /claude-wr) – e-mails that wrongly became READY_FOR_APPROVAL before the fix.

Expected outcomes come from data/erp_contracts.json, not from the code:
MV-10245 = Max Mustermann, Musterstraße 12 (OBJ-MS12, 12345 Musterstadt), 2. OG links.
"""

from __future__ import annotations

import pytest

from intake.context import Context
from intake.erp import JsonERP
from intake.matching import match
from intake.models import Extraction, InboundEmail
from intake.pipeline import process
from intake.providers.offline import OfflineProvider
from intake.rules import load_rules

RULES = load_rules()
MAX = "max.mustermann@example.org"


def run(location: str, damage: str = "Wasser läuft aus der Spüle.") -> object:
    ctx = Context.build(provider=OfflineProvider())
    body = f"{damage} {location}\nViele Grüße, Max Mustermann"
    return process(InboundEmail(subject="Schaden", body=body, sender_email=MAX), ctx)


# --- A: another town / postcode next to the address -> building unclear ---------------------
@pytest.mark.parametrize("location", [
    "Musterstraße 12 in Anderstadt, 2. OG links.",
    "Ich wohne in der Musterstraße 12 in Anderstadt im 2. OG links.",
    "Musterstraße 12, 54321 Anderstadt, 2. OG links.",
    "54321 Anderstadt, Musterstraße 12, 2. OG links.",
    "Musterstraße 12 in 54321 Anderstadt, 2. OG links.",
    "Musterstraße 12, 54321, 2. OG links.",
])
def test_other_town_or_postcode_is_review(location):
    case = run(location)
    assert case.status.value == "NEEDS_REVIEW" and case.match.selected_contract is None
    assert case.match.building_uncertain is True and case.match.object_id is None


@pytest.mark.parametrize("location", [
    "Musterstraße 12, 12345 Musterstadt, 2. OG links.",
    "Musterstraße 12 in Musterstadt, 2. OG links.",
    "12345 Musterstadt, Musterstraße 12, 2. OG links.",
    "Musterstraße 12\n12345 Musterstadt\n2. OG links",
])
def test_correct_postcode_and_town_stay_ready(location):
    case = run(location)
    assert case.status.value == "READY_FOR_APPROVAL" and case.match.selected_contract == "MV-10245"


def test_postcode_is_not_a_second_house_number():
    e = OfflineProvider().understand(InboundEmail(body="Musterstraße 12, 12345 Musterstadt, 2. OG links."), RULES).extraction
    assert e.house_no == "12" and e.postal_raw == "12345 Musterstadt"


@pytest.mark.parametrize("postal,ready", [("12345 Musterstadt", True), ("12345", True), ("Musterstadt", True),
                                          ("54321 Musterstadt", False), ("12345 Anderstadt", False),
                                          ("Anderstadt", False)])
def test_postal_check_is_provider_independent(postal, ready):
    ext = Extraction(tenant_name="Max Mustermann", sender_name="Max Mustermann", street_raw="Musterstraße",
                     house_no="12", floor_raw="2. OG", side_raw="links", postal_raw=postal)
    r = match(ext, InboundEmail(body="x", sender_email=MAX), JsonERP(), RULES)
    assert (r.selected_contract == "MV-10245") is ready
    assert r.building_uncertain is (not ready)


# --- B: other part of the property -> building unclear -------------------------------------
@pytest.mark.parametrize("location", [
    "Musterstraße 12, Hinterhaus, 2. OG links.",
    "Musterstraße 12\nHinterhaus\n2. OG links",
    "Musterstraße 12, Haus B, 2. OG links.",
    "Musterstraße 12, Aufgang 2, 2. OG links.",
    "Im Seitenflügel der Musterstraße 12, 2. OG links.",
])
def test_building_part_is_review(location):
    case = run(location)
    assert case.status.value == "NEEDS_REVIEW" and case.match.selected_contract is None
    assert case.match.building_uncertain is True and case.match.object_id is None


# --- C: flat number -> unit unclear, building stays certain -------------------------------------
@pytest.mark.parametrize("location", [
    "Musterstraße 12, Wohnung 5, 2. OG links.",
    "Musterstraße 12, 2. OG links, Wohnung 5.",
    "Musterstraße 12, 2. OG Wohnung 5 links.",
    "Musterstraße 12, 2. OG links, Whg. Nr. 5.",
])
def test_flat_number_is_unit_review(location):
    case = run(location)
    assert case.status.value == "NEEDS_REVIEW" and case.match.selected_contract is None
    assert case.match.building_uncertain is False and case.match.object_id == "OBJ-MS12"


# --- controls: normal e-mails keep their result ------------------------------------------------
@pytest.mark.parametrize("location,damage,urgency", [
    ("Musterstraße 12, im ganzen Haus riecht es nach Gas, 2. OG links.", "Hilfe!", "NOTFALL"),
    ("In der Musterstraße 12 ist im 2. OG links ein Rohr geplatzt.", "Notfall!", "NOTFALL"),
    ("Musterstraße 12 in der Küche ist ein Rohr geplatzt, 2. OG links.", "Notfall!", "NOTFALL"),
    ("Musterstraße 12, im Eingang steht Wasser, 2. OG links.", "Wasser läuft aus der Spüle.", "DRINGEND"),
    ("Musterstraße 12, zweite Etage links.", "Wasser läuft aus der Spüle.", "DRINGEND"),
    ("Musterstraße 12 im zweiten Stock links. We need help.", "Wasser läuft aus der Spüle.", "DRINGEND"),
])
def test_controls_stay_ready(location, damage, urgency):
    case = run(location, damage)
    assert case.status.value == "READY_FOR_APPROVAL" and case.match.selected_contract == "MV-10245"
    assert case.match.object_id == "OBJ-MS12" and case.urgency.level.value == urgency


def test_house_number_lists_unchanged():
    reader = OfflineProvider()
    for body, house in [("Musterstraße 12, 14, 2. OG links.", "12, 14"), ("Musterstraße 12-14, 2. OG links.", "12-14"),
                        ("Musterstraße 12, 2. OG links.", "12")]:
        assert reader.understand(InboundEmail(body=body), RULES).extraction.house_no == house


# --- build review round 1 ------------------------------------------------------------------
def test_address_block_after_negated_damage_line_keeps_building():
    ctx = Context.build(provider=OfflineProvider())
    body = "Hallo,\nes riecht nach Gas und der Geruch geht nicht weg\nMusterstraße 12\nMax Mustermann"
    case = process(InboundEmail(subject="Gas", body=body, sender_email=MAX), ctx)
    assert case.urgency.level.value == "NOTFALL" and case.match.object_id == "OBJ-MS12"
    assert case.internal_task.scope == "object"


@pytest.mark.parametrize("body", ["Hallo,\ndie Heizung geht nicht\nMusterstraße 12\n2. OG links\nMax Mustermann",
                                  "Musterstraße 12, 2. OG links\nKein Warmwasser seit gestern\nMax Mustermann"])
def test_line_style_e_mails_stay_ready(body):
    ctx = Context.build(provider=OfflineProvider())
    case = process(InboundEmail(subject="Schaden", body=body, sender_email=MAX), ctx)
    assert case.status.value == "READY_FOR_APPROVAL" and case.match.selected_contract == "MV-10245"


@pytest.mark.parametrize("location", [
    "Ich wohne in der Musterstraße 12 in Anderstadt. Im 2. OG links ist es nass.",
    "In Anderstadt, Musterstraße 12, 2. OG links.",
    "Ich wohne in Anderstadt in der Musterstraße 12 im 2. OG links.",
])
def test_more_town_phrasings_are_review(location):
    case = run(location)
    assert case.status.value == "NEEDS_REVIEW" and case.match.building_uncertain is True


def test_in_flammen_is_not_a_town():
    case = run("Musterstraße 12 in Flammen, 2. OG links, bitte Feuerwehr!", "Notfall, Kurzschluss!")
    assert case.understanding.extraction.postal_raw is None and case.match.object_id == "OBJ-MS12"


@pytest.mark.parametrize("location", ["Musterstraße 12, im Eingang 2 cm Wasser, 2. OG links.",
                                      "Musterstraße 12, Wohnung 2. OG links."])
def test_measures_and_floor_numbers_are_not_designators(location):
    case = run(location)
    assert case.status.value == "READY_FOR_APPROVAL" and case.match.object_id == "OBJ-MS12"


@pytest.mark.parametrize("location", ["Musterstraße 12, 2. OG links, Wohnungsnummer: 5.",
                                      "Musterstraße 12, 2. OG links, Whg.-Nr. 5."])
def test_more_flat_number_spellings_are_unit_review(location):
    case = run(location)
    assert case.status.value == "NEEDS_REVIEW" and case.match.object_id == "OBJ-MS12"


def test_proxy_and_postcode_checks_apply_to_ai_readers():
    """An AI reader cannot fill on_behalf_of/postal_raw (not in its schema): fixed rules add them for every reader."""
    from intake.models import Classification, MessageType, Understanding

    class FakeAI:
        name = "groq"

        def understand(self, email, rules):
            ext = Extraction(tenant_name="Max Mustermann", sender_name="Max Mustermann", street_raw="Musterstraße",
                             house_no="12", floor_raw="2. OG", side_raw="links")
            cls = Classification(type=MessageType.SCHADENMELDUNG, category="Wasserschaden", trade="Sanitär",
                                 confidence=0.9, reason="test")
            return Understanding(classification=cls, extraction=ext, provider="groq")

    ctx = Context.build(provider=FakeAI())
    for body, gate in [("Wasser läuft aus. Ich schreibe für meine Mutter. Musterstraße 12, 2. OG links.", "identity"),
                       ("Wasser läuft aus. Musterstraße 12, 54321 Anderstadt, 2. OG links.", "unit_ambiguous")]:
        case = process(InboundEmail(subject="Schaden", body=body, sender_email=MAX), ctx)
        assert case.status.value == "NEEDS_REVIEW" and gate in {g.value for g in case.match.failed_gates}


# --- build review round 2 ------------------------------------------------------------------
@pytest.mark.parametrize("text", ["Ich wohne nicht mehr in der\nMusterstraße 12, 2. OG links.",
                                  "Wir wohnen nicht mehr in der\n2. Etage links, Musterstraße 12."])
def test_mail_client_wrap_before_street_or_floor_keeps_negation(text):
    ctx = Context.build(provider=OfflineProvider())
    case = process(InboundEmail(subject="Schaden", body=f"Wasser läuft aus der Spüle. {text}\nViele Grüße, Max Mustermann",
                                sender_email=MAX), ctx)
    assert case.status.value == "NEEDS_REVIEW" and case.match.selected_contract is None


@pytest.mark.parametrize("location", ["Musterstraße 12 in Lebensgefahr! 2. OG links.",
                                      "Musterstraße 12 in Hausflur, 2. OG links."])
def test_states_and_rooms_after_in_are_not_towns(location):
    case = run(location, "Notfall, Rohrbruch!")
    assert case.understanding.extraction.postal_raw is None and case.match.object_id == "OBJ-MS12"


def test_ai_reader_postal_follows_its_own_address():
    from intake.models import Classification, MessageType, Understanding

    class FakeAI:
        name = "groq"

        def understand(self, email, rules):
            ext = Extraction(tenant_name="Max Mustermann", sender_name="Max Mustermann", street_raw="Musterstraße",
                             house_no="12", floor_raw="2. OG", side_raw="links")
            cls = Classification(type=MessageType.SCHADENMELDUNG, category=None, trade=None, confidence=0.9,
                                 reason="test")
            return Understanding(classification=cls, extraction=ext, provider="groq")

    body = ("Hausmeister Beispielweg 7 ist informiert. Wasser läuft aus. Wir wohnen Musterstraße 12 in Anderstadt, "
            "2. OG links. Max Mustermann")
    case = process(InboundEmail(subject="Schaden", body=body, sender_email=MAX), Context.build(provider=FakeAI()))
    assert case.understanding.extraction.postal_raw == "Anderstadt" and case.status.value == "NEEDS_REVIEW"


def test_multi_word_town_prefix_matches():
    from intake.erp import Property

    class OneProperty(JsonERP):
        def properties(self):
            return [Property(object_id="OBJ-MS12", street="Musterstraße", house_no="12", zip="60311",
                             city="Frankfurt am Main")]
    ext = Extraction(tenant_name="Max Mustermann", sender_name="Max Mustermann", street_raw="Musterstraße",
                     house_no="12", floor_raw="2. OG", side_raw="links", postal_raw="60311 Frankfurt")
    r = match(ext, InboundEmail(body="x", sender_email=MAX), OneProperty(), RULES)
    assert r.selected_contract == "MV-10245"


@pytest.mark.parametrize("location", ["Musterstraße 12, 2. OG links, Wohnung 3 Zimmer.",
                                      "Musterstraße 12, 2. OG links, Wohnung 12 Jahre alt."])
def test_flat_size_or_age_is_not_a_flat_number(location):
    case = run(location)
    assert case.status.value == "READY_FOR_APPROVAL"


# --- build review round 3 ------------------------------------------------------------------
@pytest.mark.parametrize("text", ["Ich wohne nicht mehr in der \nMusterstraße 12, 2. OG links.",
                                  "Ich wohne nicht mehr in der\r\nMusterstraße 12, 2. OG links."])
def test_trailing_space_and_crlf_do_not_hide_negation(text):
    ctx = Context.build(provider=OfflineProvider())
    case = process(InboundEmail(subject="Schaden", body=f"Wasser läuft aus der Spüle. {text}\nViele Grüße, Max Mustermann",
                                sender_email=MAX), ctx)
    assert case.status.value == "NEEDS_REVIEW" and case.match.selected_contract is None


@pytest.mark.parametrize("location,damage", [("Musterstraße 12 in Gästebad, 2. OG links.", "Rohrbruch!"),
                                             ("Musterstraße 12, im Haus 3 Wohnungen betroffen, 2. OG links.",
                                              "Es riecht nach Gas!")])
def test_rooms_and_counts_keep_the_building(location, damage):
    case = run(location, damage)
    assert case.match.object_id == "OBJ-MS12" and case.urgency.level.value == "NOTFALL"


def test_real_town_ending_in_haus_is_checked():
    case = run("Musterstraße 12 in Neuhaus, 2. OG links.")
    assert case.understanding.extraction.postal_raw == "Neuhaus" and case.status.value == "NEEDS_REVIEW"


# --- build review round 4 ------------------------------------------------------------------
@pytest.mark.parametrize("damage", ["die Heizung geht nicht mehr", "es kommt kein Warmwasser mehr"])
def test_damage_line_ending_in_nicht_mehr_keeps_address(damage):
    ctx = Context.build(provider=OfflineProvider())
    case = process(InboundEmail(subject="Schaden", body=f"Hallo,\n{damage}\nMusterstraße 12\n2. OG links\nMax Mustermann",
                                sender_email=MAX), ctx)
    assert case.status.value == "READY_FOR_APPROVAL" and case.match.selected_contract == "MV-10245"


def test_gas_emergency_line_ending_in_nicht_mehr_keeps_object_task():
    ctx = Context.build(provider=OfflineProvider())
    body = "Es riecht nach Gas! Der Herd geht nicht mehr\nMusterstraße 12\nMax Mustermann"
    case = process(InboundEmail(subject="Gas", body=body, sender_email=MAX), ctx)
    assert case.urgency.level.value == "NOTFALL" and case.match.object_id == "OBJ-MS12"
    assert case.internal_task.scope == "object"


def test_living_there_no_longer_on_previous_line_is_review():
    ctx = Context.build(provider=OfflineProvider())
    body = "Wasser läuft aus der Spüle. Wir wohnen nicht mehr\nMusterstraße 12, 2. OG links\nMax Mustermann"
    case = process(InboundEmail(subject="Schaden", body=body, sender_email=MAX), ctx)
    assert case.status.value == "NEEDS_REVIEW" and case.match.selected_contract is None


# --- build review round 5 (minor findings) -------------------------------------------------
def test_living_verb_then_preposition_line_is_review():
    ctx = Context.build(provider=OfflineProvider())
    body = "Wasser läuft aus der Spüle. Wir wohnen nicht mehr\nIn der Musterstraße 12, 2. OG links\nMax Mustermann"
    case = process(InboundEmail(subject="Schaden", body=body, sender_email=MAX), ctx)
    assert case.status.value == "NEEDS_REVIEW" and case.match.selected_contract is None


def test_partnerin_is_recorded_completely():
    e = OfflineProvider().understand(InboundEmail(body="Ich schreibe für meine Partnerin. Musterstraße 12."), RULES).extraction
    assert e.on_behalf_of == "für meine Partnerin"


@pytest.mark.parametrize("town", ["Bad Homburg", "Hof"])
def test_real_short_town_names_are_checked(town):
    case = run(f"Musterstraße 12 in {town}, 2. OG links.")
    assert case.understanding.extraction.postal_raw == town and case.status.value == "NEEDS_REVIEW"


def test_room_word_after_in_is_not_a_town():
    case = run("Musterstraße 12 in Küche Wasser, 2. OG links.")
    assert case.understanding.extraction.postal_raw is None and case.match.object_id == "OBJ-MS12"


def test_next_sentence_word_is_not_part_of_the_town():
    case = run("Musterstraße 12, 12345 Musterstadt Ich wohne im 2. OG links.")
    assert case.understanding.extraction.postal_raw == "12345 Musterstadt"


def test_new_flag_texts_have_english():
    from intake.i18n import translate
    r = match(Extraction(tenant_name="Max Mustermann", sender_name="Max Mustermann", street_raw="Musterstraße",
                         house_no="12", floor_raw="2. OG", side_raw="links", postal_raw="54321 Anderstadt",
                         on_behalf_of="für meine Mutter"),
              InboundEmail(body="x", sender_email=MAX), JsonERP(), RULES)
    texts = [f.message for f in r.flags if "PLZ/Ort" in f.message or "andere Person" in f.message]
    assert len(texts) == 2 and all(translate(t) for t in texts)


# --- Codex round 18 ---------------------------------------------------------------------
@pytest.mark.parametrize("extra,building", [("Wir wohnen im Hinterhaus.", True), ("Es ist die Wohnung 5.", False)])
def test_qualifier_in_another_sentence_is_review(extra, building):
    case = run(f"Musterstraße 12, zweite Etage links. {extra}")
    assert case.status.value == "NEEDS_REVIEW" and case.match.building_uncertain is building


def test_qualifier_in_subject_is_review():
    ctx = Context.build(provider=OfflineProvider())
    case = process(InboundEmail(subject="Wasserschaden Hinterhaus", body="Wasser läuft aus der Spüle. Musterstraße 12, "
                                "zweite Etage links. Viele Grüße, Max Mustermann", sender_email=MAX), ctx)
    assert case.status.value == "NEEDS_REVIEW" and case.match.building_uncertain is True


@pytest.mark.parametrize("extra,building", [("Wir wohnen im Hinterhaus.", True), ("Es ist Wohnung 5.", False)])
def test_ai_reader_gets_qualifier_checks(extra, building):
    from intake.models import Classification, MessageType, Understanding

    class FakeAI:
        name = "groq"

        def understand(self, email, rules):
            ext = Extraction(tenant_name="Max Mustermann", sender_name="Max Mustermann", street_raw="Musterstraße",
                             house_no="12", floor_raw="zweite Etage", side_raw="links")
            cls = Classification(type=MessageType.SCHADENMELDUNG, category=None, trade=None, confidence=0.9,
                                 reason="test")
            return Understanding(classification=cls, extraction=ext, provider="groq")

    body = f"Wasser läuft aus. Musterstraße 12, zweite Etage links. {extra} Max Mustermann"
    case = process(InboundEmail(subject="Schaden", body=body, sender_email=MAX), Context.build(provider=FakeAI()))
    assert case.status.value == "NEEDS_REVIEW" and case.match.building_uncertain is building


def test_crlf_address_block_postcode_is_checked():
    ctx = Context.build(provider=OfflineProvider())
    body = "Wasser läuft aus der Spüle.\r\nMusterstraße 12\r\n54321 Anderstadt\r\n2. OG links.\r\nViele Grüße, Max Mustermann"
    case = process(InboundEmail(subject="Schaden", body=body, sender_email=MAX), ctx)
    assert case.understanding.extraction.postal_raw == "54321 Anderstadt" and case.status.value == "NEEDS_REVIEW"
