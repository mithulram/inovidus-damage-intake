"""Deterministic keyword classification and raw-span extraction; no network calls."""

from __future__ import annotations

import re

from ..models import Classification, Extraction, InboundEmail, MessageType, Understanding
from ..normalize import fold
from ..rules import Rules

_NAME_WORD = r"(?:[A-ZÄÖÜ][a-zäöüßéèáà'-]+|[A-ZÄÖÜ]\.)"
_NAME = rf"{_NAME_WORD}(?:[ \t]+{_NAME_WORD}){{1,3}}"
_ADDRESS = re.compile(
    r"\b(?P<street>[A-ZÄÖÜa-zäöüß][\w-]*?(?:str\.|straße|strasse|weg|platz|allee|gasse|ring))"
    r"\s+(?P<number>\d+[ \t]?[a-z]?)\b", re.IGNORECASE,
)


def _hits(text: str, keywords: list[str]) -> list[str]:
    return [word for word in keywords if fold(word) in text]


def _raw(pattern: str, text: str) -> str | None:
    hit = re.search(pattern, text, re.IGNORECASE)
    return hit.group(0) if hit else None


def _floor(text: str, rules: Rules) -> re.Match | None:
    terms = sorted(rules.normalize.ground_floor_terms + rules.normalize.unclear_floor_terms,
                   key=len, reverse=True)
    ordinals = "|".join(map(re.escape, rules.normalize.ordinal_words))
    pattern = (
        r"\b(?:(?:im\s+)?(?:\d+\s*\.?\s*|(?:" + ordinals + r")\s+)"
        r"(?:Obergeschoss|Stockwerk|Etage|Stock|OG)\b"
        r"|(?:\d+\s*(?:st|nd|rd|th)|first|second|third|fourth|fifth)\s+floor\b"
        r"|(?:" + "|".join(map(re.escape, terms)) + r")\b)"
    )
    return re.search(pattern, text, re.IGNORECASE)


def _signature(body: str) -> str | None:
    closing = re.search(
        rf"(?i:Viele\s+Grüße|Grüße|LG|Best\s+regards|Regards)[,\s:]+(?P<name>{_NAME})", body,
    )
    if closing:
        return closing.group("name")
    trailing = re.search(rf"(?P<name>{_NAME})[.!\s]*$", body)
    return trailing.group("name") if trailing else None


class OfflineProvider:
    name = "offline"
    model = None

    def understand(self, email: InboundEmail, rules: Rules) -> Understanding:
        text = f"{email.subject}\n{email.body}"
        folded = fold(text)
        cfg = rules.classification
        damage_hits = _hits(folded, cfg.damage_keywords)
        message_type = MessageType.SONSTIGES
        type_hits = damage_hits
        if damage_hits:
            message_type = MessageType.SCHADENMELDUNG
        else:
            for name, route in cfg.out_of_scope.items():
                if hits := _hits(folded, route.keywords):
                    message_type, type_hits = MessageType(name), hits
                    break
        category = next((c for c in cfg.categories if _hits(folded, c.keywords)), None)
        keywords = list(dict.fromkeys(type_hits + (_hits(folded, category.keywords) if category else [])))
        classification = Classification(
            type=message_type, category=category.name if category else None,
            trade=category.trade if category else None, confidence=0.9 if category else 0.6,
            reason="Regelmodus; gefundene Schlüsselwörter: " + (", ".join(keywords) or "keine") + ".",
        )
        # Prefer facts in the body; the subject remains a fallback source.
        raw_text = f"{email.body}\n{email.subject}"
        address = _ADDRESS.search(raw_text)
        floor = _floor(raw_text, rules)
        anchors = [m for m in (address, floor) if m]
        side = None
        side_terms = sorted({t for values in rules.normalize.side_terms.values() for t in values},
                            key=len, reverse=True)
        side_pattern = r"(?<!\w)(?:" + "|".join(map(re.escape, side_terms)) + r")(?!\w)"
        for anchor in anchors:
            nearby = raw_text[max(0, anchor.start() - 35):anchor.end() + 55]
            side = _raw(side_pattern, nearby)
            if side:
                break
        sender_name = _signature(email.body)
        holder = re.search(rf"(?i:Wohnung\s+von|für\s+meinen\s+Partner)\s+({_NAME})", email.body)
        room = next((r for r in cfg.rooms if fold(r) in folded), None)
        description = next((s.strip() for s in re.split(r"(?<=[.!?])\s+", email.body)
                            if _hits(fold(s), cfg.damage_keywords)), None)
        tokens = re.findall(r"\b\w+\b", folded)
        english = {"the", "is", "our", "we", "under", "and", "since", "please", "hello", "at", "in", "of"}
        german = {"der", "die", "das", "ist", "wir", "unter", "und", "seit", "bitte", "hallo", "in", "im", "von"}
        language = "en" if sum(t in english for t in tokens) > sum(t in german for t in tokens) else "de"
        extraction = Extraction(
            sender_name=sender_name, tenant_name=holder.group(1) if holder else sender_name,
            street_raw=address.group("street") if address else None,
            house_no=address.group("number") if address else None,
            floor_raw=floor.group(0) if floor else None, side_raw=side, room=room,
            damage_description=description,
            since=_raw(r"\b(?:seit\s+(?:gestern|heute(?:\s+(?:Morgen|Nacht))?)|since\s+yesterday)\b", email.body),
            photos_mentioned=bool(re.search(r"\b(?:Fotos?|Bilder|photos?)\b", text, re.IGNORECASE)),
            phone=_raw(r"(?<!\w)(?:\+\d{1,3}[ \t-]*|0)(?:\(?\d\)?[ \t/()-]*){6,}\d(?!\w)", email.body),
            language=language,
        )
        return Understanding(classification=classification, extraction=extraction, provider=self.name)
