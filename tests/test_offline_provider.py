"""WO1: rule-based classification and raw extraction, without a live provider."""

import socket

import pytest

from intake.models import InboundEmail, MessageType
from intake.normalize import normalize_floor, normalize_side
from intake.providers.offline import OfflineProvider
from intake.rules import load_rules


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
    ("Musterstr.", "12"), ("Musterstraße", "16"), ("Musterstrasse", "12"),
    ("Beispielweg", "7a"), ("Testplatz", "3"), ("Testallee", "4"),
    ("Testgasse", "5"), ("Testring", "6"),
])
def test_address_is_copied_as_written(rules, street, number):
    result = OfflineProvider().understand(InboundEmail(body=f"Wasser bei {street} {number}, 2. OG links."), rules)
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
    assert extraction.room == ("kitchen" if language == "en" else "küche")
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
