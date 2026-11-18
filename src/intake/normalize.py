"""Deterministic normalisation of address, floor and side.

The LLM (or the offline rules) only copies raw text spans such as "zweite Etage links".
Turning them into comparable values happens here, so the result is reproducible and
explainable: "zweite Etage" -> 2, "li." -> L, "Musterstr." -> "musterstraße".
"""

from __future__ import annotations

import re
import unicodedata

from .models import NormalizedLocation, Side
from .rules import NormalizeRules

_STREET_SUFFIX = re.compile(r"(str\.?|strasse|straße)$")


def fold(text: str | None) -> str:
    """Lowercase, trim, unify whitespace and German special characters for comparison."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text).lower().strip()
    text = text.replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    return re.sub(r"\s+", " ", text)


def normalize_street(street: str | None) -> str | None:
    """"Musterstr." / "Musterstrasse" / "Musterstraße" -> "musterstrasse"."""
    if not street:
        return None
    s = fold(street).rstrip(" ,.")
    s = re.sub(r"[\s-]+", "", s)
    s = _STREET_SUFFIX.sub("strasse", s) if not s.endswith("strasse") else s
    return s or None


def normalize_house_no(house_no: str | None) -> str | None:
    if not house_no:
        return None
    return re.sub(r"\s+", "", house_no.lower()) or None


def normalize_floor(raw: str | None, rules: NormalizeRules) -> tuple[int | None, str, str | None]:
    """Return (floor, status, note). German counting: EG = 0, 1. OG / erste Etage = 1.

    status: ok | missing | unclear | english_ordinal
    """
    if not raw or not raw.strip():
        return None, "missing", "Keine Etage angegeben"
    text = fold(raw)
    folded_ground = [fold(t) for t in rules.ground_floor_terms]
    if any(re.search(rf"(^|\W){re.escape(t)}(\W|$)", text) for t in folded_ground):
        return 0, "ok", f"'{raw}' = Erdgeschoss (EG)"

    # English ordinals: "2nd floor", "second floor"
    m_en = re.search(r"\b(\d+)\s*(st|nd|rd|th)\b", text)
    en_words = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
    m_en_word = re.search(r"\b(" + "|".join(en_words) + r")\s+floor\b", text)
    if m_en or m_en_word:
        n = int(m_en.group(1)) if m_en else en_words[m_en_word.group(1)]
        return n, "english_ordinal", (
            f"'{raw}' als {n}. OG gelesen (britische/europäische Zählweise); "
            f"in US-Zählweise wäre es das {n - 1}. OG" if n > 0 else f"'{raw}' als {n}. OG gelesen"
        )

    # German: "2. OG", "2. Etage", "2. Stock", "2 OG"
    m_de = re.search(r"\b(\d+)\s*\.?\s*(og|obergeschoss|etage|stock|stockwerk)\b", text)
    if m_de:
        n = int(m_de.group(1))
        return n, "ok", f"'{raw}' = {n}. OG"
    # German ordinal words: "zweite Etage", "im dritten Stock"
    words = {fold(k): v for k, v in rules.ordinal_words.items()}
    m_word = re.search(r"\b(" + "|".join(map(re.escape, words)) + r")\s+(og|obergeschoss|etage|stock|stockwerk)\b", text)
    if m_word:
        n = words[m_word.group(1)]
        return n, "ok", f"'{raw}' = {n}. OG"

    folded_unclear = [fold(t) for t in rules.unclear_floor_terms]
    if any(re.search(rf"(^|\W){re.escape(t)}(\W|$)", text) for t in folded_unclear):
        return None, "unclear", f"'{raw}' ist keine eindeutige Etage"
    return None, "unclear", f"'{raw}' konnte keiner Etage zugeordnet werden"


def normalize_side(raw: str | None, rules: NormalizeRules) -> Side | None:
    if not raw:
        return None
    text = fold(raw)
    tokens = re.findall(r"[a-z]+\.?", text)
    for side, terms in rules.side_terms.items():
        folded = {fold(t) for t in terms}
        if any(tok in folded or tok.rstrip(".") in folded for tok in tokens):
            return side
    return None


def normalize_location(
    street_raw: str | None,
    house_no: str | None,
    floor_raw: str | None,
    side_raw: str | None,
    rules: NormalizeRules,
) -> NormalizedLocation:
    floor, status, note = normalize_floor(floor_raw, rules)
    return NormalizedLocation(
        street=normalize_street(street_raw),
        house_no=normalize_house_no(house_no),
        floor=floor,
        floor_status=status,  # type: ignore[arg-type]
        floor_note=note,
        side=normalize_side(side_raw, rules),
    )
