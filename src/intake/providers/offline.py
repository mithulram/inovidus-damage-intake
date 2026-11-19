"""Deterministic keyword classification and raw-span extraction; no network calls."""

from __future__ import annotations

import re

from ..models import Classification, Extraction, InboundEmail, MessageType, Understanding
from ..normalize import fold, normalize_floor, normalize_house_no, normalize_side, normalize_street
from ..rules import Rules

_NAME_WORD = r"(?:[A-ZÄÖÜ][a-zäöüßéèáà'-]+|[A-ZÄÖÜ]\.)"
_NAME = rf"{_NAME_WORD}(?:[ \t]+{_NAME_WORD}){{1,3}}"
# Keep unknown prefix words regardless of case: truncation could turn a
# different street into an ERP match. Function words delimit the street name.
_STREET_PREFIX = (
    r"(?!(?:wir|ich|der|die|das|dem|den|in|im|am|an|auf|zur|zum|bei|von|"
    r"wohnen|wohne|leben|adresse|anschrift|hallo|bitte|hilfe|notfall|außerdem|"
    r"achtung|dringend|wohnung|unsere|meine|hello|hi|help|urgent|we|at|live|the|address)\b)"
    r"[A-ZÄÖÜa-zäöüß][\w-]*\s+"
)
# Preserve unfamiliar numeric tokens too; validation must never truncate an
# unsupported suffix or decimal into a known building's house number.
_HOUSE_NUMBER = r"\d+\w*(?:\.\d+\w*)*(?:[ \t]+[a-z])?(?!\w)"
# A comma before a floor ("12, 2. OG") ends the house-number expression.
# Letter endpoints stay literal: "12a-c" contributes "c", never an invented "12c".
_HOUSE_NUMBER_EXTRA = (
    rf"(?:{_HOUSE_NUMBER}|[a-z](?!\w))"
    r"(?!\s*\.?\s*(?:Obergeschoss|Stockwerk|Etage|Stock|OG|floor)\b)"
)
_HOUSE_NUMBER_CONTINUATION = re.compile(
    rf"\s*(?:[-–—/,+&]|und\b|oder\b|bzw\.(?!\w)|bis\b)\s*(?P<extra>{_HOUSE_NUMBER_EXTRA})", re.IGNORECASE,
)
_ADDRESS = re.compile(
    # "am" alone is a function word, but retain it before another prefix word
    # in names such as "Am alten Musterweg". Capture at most two prefix words.
    rf"\b(?P<street>(?:(?:am\s+|{_STREET_PREFIX})?{_STREET_PREFIX})?"
    r"[A-ZÄÖÜa-zäöüß][\w-]*?(?:straße|strasse|str\.?|weg|platz|allee|gasse|ring))"
    rf"\s*(?P<number>{_HOUSE_NUMBER}(?:{_HOUSE_NUMBER_CONTINUATION.pattern})*"
    # Preserve unsupported attached tails too, rather than reporting "12" for
    # "12-" or "12/foo". They become literal uncertainty evidence below.
    r"(?:[ \t]*[-–—/][ \t]*[^\s,;.!?]*)*)", re.IGNORECASE,
)
_LOCATION_REFERENCE = re.compile(
    r"\b(?:Etage|Stockwerk|Stock|Geschoss|Obergeschoss|Hausnummer|Hausnr\.?|Haus|Adresse|Anschrift|"
    r"Straße|Strasse|Str\.?|Wohnungsseite|floor|address|street|house\s+number|apartment\s+side)(?!\w)",
    re.IGNORECASE,
)


def _hits(text: str, keywords: list[str], *, whole_words: bool = False) -> list[str]:
    # Category evidence must match complete words/phrases, not parts of other words.
    # General damage stems and urgency phrases retain their configured semantics.
    return [word for word in keywords
            if (re.search(rf"(?<!\w){re.escape(fold(word))}(?!\w)", text)
                if whole_words else fold(word) in text)]


def _raw(pattern: str, text: str) -> str | None:
    hit = re.search(pattern, text, re.IGNORECASE)
    return hit.group(0) if hit else None


def _floors(text: str, rules: Rules, start: int, end: int) -> list[re.Match]:
    terms = sorted(rules.normalize.ground_floor_terms + rules.normalize.unclear_floor_terms,
                   key=len, reverse=True)
    ordinals = "|".join(map(re.escape, rules.normalize.ordinal_words))
    pattern = (
        r"\b(?:(?:im\s+)?(?:\d+\s*\.?\s*|(?:" + ordinals + r")\s+)"
        r"(?:Obergeschoss|Stockwerk|Etage|Stock|OG)\b"
        r"|(?:\d+\s*(?:st|nd|rd|th)|first|second|third|fourth|fifth)\s+floor\b"
        r"|(?:" + "|".join(map(re.escape, terms)) + r")\b)"
    )
    # A shared suffix still describes every preceding choice: "2. bzw. 3. OG",
    # "zweite oder dritte Etage", "2nd or 3rd floor". Keep each literal operand
    # before selecting a primary floor; never synthesize a missing suffix.
    abbreviated = re.compile(
        r"\b(?P<abbreviated>(?:im\s+)?(?:\d+(?:\s*(?:st|nd|rd|th|\.))?"
        r"|(?:" + ordinals + r")|first|second|third|fourth|fifth))(?!\w)",
        re.IGNORECASE,
    )
    connector = r"(?:bzw\.(?!\w)|oder\b|or\b|bis\b|[-–—/])"
    # "und", "to" and commas join floors too ("zwischen 2. und 3. OG", "erste, zweite Etage"), but only
    # after an operand that is clearly a floor (ordinal dot or word) – "Musterstr. 12, 2. OG" stays one floor.
    strict = (r"(?:\d+\s*(?:st|nd|rd|th|\.)|(?:" + ordinals + r")|first|second|third|fourth|fifth)(?!\w)")
    list_connector = r"(?:und\b|and\b|to\b|,)"
    unit = rf"(?:{abbreviated.pattern}\s*{connector}\s*|\b{strict}\s*{list_connector}\s*)"
    prefix_pattern = re.compile(rf"(?:{unit})+$", re.IGNORECASE)
    floors = []
    previous_end = start
    for floor in re.compile(pattern, re.IGNORECASE).finditer(text, start, end):
        prefix = prefix_pattern.search(text, previous_end, floor.start())
        if prefix:
            floors.extend(abbreviated.finditer(text, prefix.start(), prefix.end()))
        floors.append(floor)
        previous_end = floor.end()
    return floors


def _near(left: re.Match, right: re.Match, distance: int = 55) -> bool:
    first, last = sorted((left, right), key=lambda m: m.start())
    return last.start() - first.end() <= distance


def _location_alternatives(
    text: str, addresses: list[re.Match], floors: list[re.Match], sides: list[re.Match], rules: Rules,
    body_end: int,
) -> list[str]:
    """Keep literal evidence of distinct locations and location-related uncertainty."""
    def floor_key(match: re.Match) -> int | str:
        floor = normalize_floor(match.group(0), rules.normalize)[0]
        return floor if floor is not None else fold(match.group(0))

    def same_sentence(left: re.Match, right: re.Match) -> bool:
        first, last = sorted((left, right), key=lambda m: m.start())
        # Punctuation inside location tokens ("Musterstr.", "2. OG", "li.")
        # is not a sentence boundary; only inspect the gap between tokens.
        return re.search(r"[.!?]", text[first.end():last.start()]) is None

    spans = []
    # The full house-number expression belongs to the address. Keep each extra
    # endpoint verbatim as well, so the matcher treats the building as uncertain.
    for address in addresses:
        start, stop = address.span("number")
        end = re.match(_HOUSE_NUMBER, text[start:stop], re.IGNORECASE).end() + start
        while alternative := _HOUSE_NUMBER_CONTINUATION.match(text, end, stop):
            spans.append(alternative.span("extra"))
            end = alternative.end()
        if end < stop:
            spans.append((start, stop))
    for matches, key in (
        (addresses, lambda m: (normalize_street(m.group("street")), normalize_house_no(m.group("number")))),
        (floors, floor_key),
        (sides, lambda m: normalize_side(m.group(0), rules.normalize)),
    ):
        seen = set()
        for match in matches:
            value = key(match)
            if seen and value not in seen:
                end = match.end()
                # A floor followed directly by its side is one useful raw span.
                if matches is floors:
                    # Keep a shared suffix with intermediate alternatives too:
                    # "dritte oder vierte Etage" is literal floor evidence,
                    # whereas "dritte" alone would suggest building uncertainty.
                    if match.lastgroup == "abbreviated":
                        end = next(m.end() for m in floors
                                   if m.start() > match.start() and m.lastgroup != "abbreviated")
                    following = next((s for s in sides if s.start() >= end
                                      and re.fullmatch(r"[\s,/-]{0,15}", text[end:s.start()])), None)
                    if following:
                        end = following.end()
                spans.append((match.start(), end))
            seen.add(value)
    locations = addresses + floors + sides
    references = list(_LOCATION_REFERENCE.finditer(text))

    def referring_clause(marker: re.Match) -> tuple[int, int]:
        start, end = (0, body_end) if marker.start() < body_end else (body_end + 1, len(text))
        clause_start = start
        for boundary in re.finditer(r"[.;!?]", text[start:end]):
            pos = start + boundary.start()
            if text[pos] == "." and any(m.start() <= pos < m.end() for m in locations + references):
                continue
            if pos < marker.start():
                clause_start = pos + 1
            else:
                end = pos
                break
        start = clause_start
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        return start, end

    for marker in re.finditer(
        r"\b(?:unsicher|wei(?:ß|ss)\s+(?:ich\s+)?nicht\s+genau|glaube|vielleicht|not\s+sure|maybe|I\s+think)\b",
        text, re.IGNORECASE,
    ):
        # "Unsicher, ob die Versicherung zahlt" asks a different question even
        # when the preceding location is in the same sentence.
        if (re.match(r"\s*,?\s*(?:ob|whether|if)\b", text[marker.end():], re.IGNORECASE)
                and not any(m.start() >= marker.end() and _near(m, marker)
                            and same_sentence(m, marker)
                            and (m.start() < body_end) == (marker.start() < body_end)
                            for m in locations + references)):
            continue
        # Keep the whole clause when it contains a location or an explicit
        # reference, so "Vielleicht Musterstr. 12" retains building evidence.
        start, end = referring_clause(marker)
        if any(start <= location.start() and location.end() <= end
               and _near(location, marker) for location in locations + references):
            spans.append((start, end))
        # Line breaks inside a location are fine; body and subject are separate sources.
        elif any(_near(m, marker) and same_sentence(m, marker)
               and (m.start() < body_end) == (marker.start() < body_end) for m in locations):
            spans.append(marker.span())
    # Avoid repeating a side that is already included in an alternative floor.
    return list(dict.fromkeys(text[start:end] for start, end in sorted(set(spans))
                              if not any(a <= start and end <= b and (a, b) != (start, end)
                                         for a, b in spans)))


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
        damage_hits += [hit for category in cfg.categories
                        for hit in _hits(folded, category.keywords, whole_words=True)]
        damage_hits += [hit for rule in rules.urgency.rules for hit in _hits(folded, rule.any)]
        message_type = MessageType.SONSTIGES
        type_hits = damage_hits
        if damage_hits:
            message_type = MessageType.SCHADENMELDUNG
        else:
            for name, route in cfg.out_of_scope.items():
                if hits := _hits(folded, route.keywords):
                    message_type, type_hits = MessageType(name), hits
                    break
        category = next((c for c in cfg.categories if _hits(folded, c.keywords, whole_words=True)), None)
        keywords = list(dict.fromkeys(type_hits + (
            _hits(folded, category.keywords, whole_words=True) if category else [])))
        classification = Classification(
            type=message_type, category=category.name if category else None,
            trade=category.trade if category else None, confidence=0.9 if category else 0.6,
            reason="Regelmodus; gefundene Schlüsselwörter: " + (", ".join(keywords) or "keine") + ".",
        )
        # Prefer facts in the body; the subject remains a fallback source.
        raw_text = f"{email.body}\n{email.subject}"
        floors = [*_floors(raw_text, rules, 0, len(email.body)),
                  *_floors(raw_text, rules, len(email.body) + 1, len(raw_text))]
        # Whitespace inside an address may include newlines, but an address
        # must never join a body prefix/number to text from the subject.
        addresses = []
        for address in [*_ADDRESS.finditer(raw_text, 0, len(email.body)),
                        *_ADDRESS.finditer(raw_text, len(email.body) + 1)]:
            # "12, 2. bzw. 3. OG" ends the address at 12. A shared floor
            # operand must not also become an alternative house number.
            stop = next((f.start() for f in floors
                         if address.start("number") <= f.start() < address.end("number")), address.end())
            if bounded := _ADDRESS.match(raw_text, address.start(), stop):
                addresses.append(bounded)
        address = addresses[0] if addresses else None
        floor = floors[0] if floors else None
        anchors = addresses + floors
        side_terms = sorted({t for values in rules.normalize.side_terms.values() for t in values},
                            key=len, reverse=True)
        side_pattern = r"(?<!\w)(?:" + "|".join(map(re.escape, side_terms)) + r")(?!\w)"
        sides = [m for m in re.finditer(side_pattern, raw_text, re.IGNORECASE)
                 if not anchors or any(_near(m, anchor) for anchor in anchors)]
        side = sides[0].group(0) if sides else None
        sender_name = _signature(email.body)
        holder = re.search(rf"(?i:Wohnung\s+von|für\s+meinen\s+Partner)\s+({_NAME})", email.body)
        room_term = next((r for r in cfg.rooms if fold(r) in folded), None)
        room = (_raw(re.escape(room_term), raw_text) or room_term.capitalize()) if room_term else None
        description = next((s.strip() for s in re.split(r"(?<=[.!?])\s+", email.body)
                            if _hits(fold(s), cfg.damage_keywords)), None)
        tokens = re.findall(r"\b\w+\b", folded)
        english = {"the", "is", "our", "we", "under", "and", "since", "please", "hello", "at", "in", "of"}
        german = {"der", "die", "das", "ist", "wir", "unter", "und", "seit", "bitte", "hallo", "in", "im", "von"}
        language = "en" if sum(t in english for t in tokens) > sum(t in german for t in tokens) else "de"
        # A negated place ("2. OG, aber nicht links") must stay visible as doubt, never as a definite value.
        negation = re.compile(r"\b(?:nicht|kein(?:e|em|en|er)?|not|no|außer|ausser|except)\s+"
                              r"(?:(?:im|in|auf|der|die|das|dem|den|the|on|in\s+the)\s+)*$", re.IGNORECASE)
        alternatives = _location_alternatives(raw_text, addresses, floors, sides, rules, len(email.body))
        for place in [*addresses, *floors, *sides]:
            if hit := negation.search(raw_text, max(0, place.start() - 40), place.start()):
                alternatives.append(raw_text[hit.start():place.end()])
        extraction = Extraction(
            sender_name=sender_name, tenant_name=holder.group(1) if holder else sender_name,
            street_raw=address.group("street") if address else None,
            house_no=address.group("number") if address else None,
            floor_raw=floor.group(0) if floor else None, side_raw=side, room=room,
            location_alternatives=list(dict.fromkeys(alternatives)),
            damage_description=description,
            since=_raw(r"\b(?:seit\s+(?:gestern|heute(?:\s+(?:Morgen|Nacht))?)|since\s+yesterday)\b", email.body),
            photos_mentioned=bool(re.search(r"\b(?:Fotos?|Bilder|photos?)\b", text, re.IGNORECASE)),
            phone=_raw(r"(?<!\w)(?:\+\d{1,3}[ \t-]*|0)(?:\(?\d\)?[ \t/()-]*){6,}\d(?!\w)", email.body),
            language=language,
        )
        return Understanding(classification=classification, extraction=extraction, provider=self.name)
