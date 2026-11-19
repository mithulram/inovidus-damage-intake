"""German → English for every text the system generates (reasons, gates, warnings, tasks, rules).

Business language stays German (reply drafts follow the tenant's language). In the UI's English
mode each German text is shown with its English translation. Translation is deterministic: ordered
sentence patterns plus a small glossary – no LLM, so it works offline and never invents content.
Unknown text returns None (the UI then shows the German original only).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from .rules import ROOT

GLOSSARY: dict[str, str] = {
    # damage categories / trades / rooms / urgency rule labels
    "Gasgeruch": "gas smell", "Rohrbruch": "burst pipe", "Wasserschaden": "water damage",
    "Rohrverstopfung": "blocked pipe", "Heizungsausfall": "heating failure", "Elektrik": "electrics",
    "Schimmel": "mould", "Fenster/Türen": "windows/doors", "Fenster": "window",
    "Gas / Heizung": "gas / heating", "Sanitär": "plumbing", "Heizung": "heating", "Elektro": "electrical",
    "Maler / Bautrocknung": "painting / drying", "Schreiner": "carpentry", "Allgemein": "general",
    "Schadenmeldung": "damage report", "Küche": "kitchen", "Bad": "bathroom", "Badezimmer": "bathroom",
    "WC": "toilet", "Schlafzimmer": "bedroom", "Wohnzimmer": "living room", "Kinderzimmer": "children's room",
    "Flur": "hallway", "Keller": "basement", "Balkon": "balcony", "Treppenhaus": "stairwell",
    "Rohrbruch / Wasser läuft durch Decke oder steht": "burst pipe / water through the ceiling or standing",
    "Wasser an Elektrik / Stromausfall": "water at electrics / power outage",
    "Heizungsausfall in der Heizperiode": "heating failure during the heating season",
    "Wasser tritt aus (Schaden schreitet fort)": "water leaking (damage is spreading)",
    "Folgeschaden sichtbar": "consequential damage visible",
    "Kein Warmwasser / Heizung außerhalb der Heizperiode": "no hot water / heating outside the heating season",
    "Mietbuchhaltung": "rent accounting", "Kundenservice": "customer service",
    "Technik / Notdienst": "technical team / emergency service", "Sachbearbeitung": "case handling",
    "links": "left", "rechts": "right", "Mitte": "centre", "li.": "left", "re.": "right",
    "Straße": "street", "Hausnummer": "house number",
    "NOTFALL": "EMERGENCY", "DRINGEND": "URGENT", "NORMAL": "NORMAL",
}


def _g(text: str) -> str:
    """Glossary lookup for a fragment; '2. OG' → '2nd floor (German count)', 'EG' → 'ground floor'."""
    text = text.strip()
    if text in GLOSSARY:
        return GLOSSARY[text]
    m = re.fullmatch(r"(\d+)\. OG", text)
    if m:
        return f"floor {m.group(1)} (German count: {m.group(1)}. OG)"
    if text == "EG":
        return "ground floor (EG)"
    if text.startswith("Technik / "):
        return "technical team / " + _g(text[len("Technik / "):])
    return text


@lru_cache(maxsize=1)
def _template_translations() -> dict[str, str]:
    data = yaml.safe_load((ROOT / "config" / "templates.yaml").read_text(encoding="utf-8"))
    return dict(data.get("translations", {}).get("en", {}))


def _tr_list(text: str) -> str:
    """Translate a '; '-joined list; items may contain '; ' themselves, so merge pieces until one translates."""
    out, buf = [], []
    for part in text.split("; "):
        buf.append(part)
        joined = "; ".join(buf)
        t = translate(joined)
        if t:
            out.append(t)
            buf = []
    if buf:
        out.append("; ".join(buf))
    return "; ".join(out)


Pattern = tuple[re.Pattern[str], object]
P: list[Pattern] = []


def rule(pattern: str):
    def deco(fn):
        P.append((re.compile(pattern, re.DOTALL), fn))
        return fn
    return deco


# ---- matching signals ----------------------------------------------------------
@rule(r"^Kein Name in der Nachricht$")
def _(m): return "No name in the message"
@rule(r"^Name stimmt überein \((\d+) %\)$")
def _(m): return f"Name matches ({m[1]} %)"
@rule(r"^Name ähnlich, aber nicht gleich \((\d+) %\)$")
def _(m): return f"Name similar but not identical ({m[1]} %)"
@rule(r"^Anderer Name \((\d+) %\)$")
def _(m): return f"Different name ({m[1]} %)"
@rule(r"^Keine Adresse in der Nachricht$")
def _(m): return "No address in the message"
@rule(r"^Adresse stimmt überein \('(.*)' = '(.*)'\)$")
def _(m): return f"Address matches ('{m[1]}' = '{m[2]}')"
@rule(r"^Adresse unvollständig \((Hausnummer|Straße) fehlt\) – zählt nicht$")
def _(m): return f"Address incomplete ({_g(m[1])} missing) – does not count"
@rule(r"^Adresse widerspricht: (Straße|Hausnummer) \('(.*)' ≠ '(.*)'\)$")
def _(m): return f"Address contradicts: {_g(m[1])} ('{m[2]}' ≠ '{m[3]}')"
@rule(r"^Keine Etage angegeben$")
def _(m): return "No floor given"
@rule(r"^'(.*)' = Erdgeschoss \(EG\)$")
def _(m): return f"'{m[1]}' = ground floor (EG)"
@rule(r"^'(.*)' = (\d+)\. OG$")
def _(m): return f"'{m[1]}' = floor {m[2]} (German count: {m[2]}. OG)"
@rule(r"^'(.*)' = (EG|\d+\. OG)$")
def _(m): return f"'{m[1]}' = {_g(m[2])}"
@rule(r"^'(.*)' als (\d+)\. OG gelesen \(britische/europäische Zählweise\); in US-Zählweise wäre es das (\d+)\. OG$")
def _(m): return f"'{m[1]}' read as {m[2]}. OG (British/European counting); in US counting it would be {m[3]}. OG"
@rule(r"^'(.*)' ist keine eindeutige Etage$")
def _(m): return f"'{m[1]}' is not an unambiguous floor"
@rule(r"^'(.*)' konnte keiner Etage zugeordnet werden$")
def _(m): return f"'{m[1]}' could not be mapped to a floor"
@rule(r"^Etage widerspricht: (.*) ≠ (.*)$")
def _(m): return f"Floor contradicts: {_g(m[1])} ≠ {_g(m[2])}"
@rule(r"^Keine Seite \(links/rechts\) angegeben$")
def _(m): return "No side (left/right) given"
@rule(r"^'(.*)' = (li\.|re\.|links|rechts|Mitte)$")
def _(m): return f"'{m[1]}' = {_g(m[2])}"
@rule(r"^Seite widerspricht: (\S+) ≠ (\S+)$")
def _(m): return f"Side contradicts: {_g(m[1])} ≠ {_g(m[2])}"
@rule(r"^Absenderadresse ist im ERP hinterlegt$")
def _(m): return "Sender address is registered in the ERP"
@rule(r"^Telefonnummer ist im ERP hinterlegt$")
def _(m): return "Phone number is registered in the ERP"
@rule(r"^Absenderadresse nicht im ERP hinterlegt$")
def _(m): return "Sender address not registered in the ERP"
@rule(r"^Keine Absenderadresse vorhanden$")
def _(m): return "No sender address available"


# ---- gates / flags / match reasons ------------------------------------------------
@rule(r"^Kein passender Vertrag im ERP gefunden$")
def _(m): return "No matching contract found in the ERP"
@rule(r"^(MV-\S+) ausgeschlossen: (.*)$")
def _(m): return f"{m[1]} excluded: {translate(m[2])}" if translate(m[2]) else None
@rule(r"^(MV-\S+): (.*)$")
def _(m): return f"{m[1]}: {translate(m[2])}" if translate(m[2]) else None
@rule(r"^(.+?); (.+)$")
def _(m):
    a, b = translate(m[1]), translate(m[2])
    return f"{a}; {b}" if a and b else None
@rule(r"^Beste Übereinstimmung ([\d.]+) liegt unter der Schwelle ([\d.]+)$")
def _(m): return f"Best match {m[1]} is below the threshold {m[2]}"
@rule(r"^Abstand zum Zweitbesten nur ([\d.]+) \(mindestens ([\d.]+)\) – (\S+) und (\S+) kommen in Frage$")
def _(m): return f"Gap to the second best only {m[1]} (minimum {m[2]}) – both {m[3]} and {m[4]} are possible"
@rule(r"^Abstand zum Zweitbesten nur ([\d.]+) \(mindestens ([\d.]+)\) – nur (\S+) übrig, aber Abstand zu 0 reicht nicht$")
def _(m): return f"Gap to the second best only {m[1]} (minimum {m[2]}) – only {m[3]} left, but the gap to 0 is not enough"
@rule(r"^Name weicht ab: '(.*)' vs\. '(.*)'$")
def _(m): return f"Name differs: '{m[1]}' vs. '{m[2]}'"
@rule(r"^Absender '(.*)' ist nicht Vertragsinhaber \((.*)\)$")
def _(m): return f"Sender '{m[1]}' is not the contract holder ({m[2]})"
@rule(r"^Nachricht nicht von der registrierten E-Mail-Adresse$")
def _(m): return "Message not sent from the registered e-mail address"
@rule(r"^Nicht von der registrierten E-Mail-Adresse$")
def _(m): return "Not from the registered e-mail address"
@rule(r"^Einheit erkannt \((.*)\), aber Vertrag (\S+) ist inaktiv – Mieterwechsel/Leerstand prüfen\. Kein Ausweichen auf einen anderen Vertrag\.$")
def _(m): return f"Unit identified ({m[1]}), but contract {m[2]} is inactive – check change of tenant / vacancy. No fallback to another contract."
@rule(r"^E-Mail nennt mehrere oder unsichere Ortsangaben: (.*) – beim Mieter nachfragen$")
def _(m): return f"The e-mail names several or uncertain locations: {m[1]} – ask the tenant"
@rule(r"^Zählweise der Etage unklar: (.*)$")
def _(m): return f"Floor counting unclear: {translate(m[1])}" if translate(m[1]) else None
@rule(r"^Eindeutig: (\S+) \((.*)\) mit ([\d.]+) Punkten, Abstand ([\d.]+)\. Bitte prüfen und freigeben\.$")
def _(m): return f"Unambiguous: {m[1]} ({m[2]}) with {m[3]} points, gap {m[4]}. Please check and approve."
@rule(r"^Prüfung nötig: (.*)$")
def _(m):
    parts = [translate(p) or p for p in m[1].split(" | ")]
    return "Review needed: " + " | ".join(parts)
@rule(r"^Keine Schadenmeldung \((\w+)\) – weiterleiten an (.*)\.$")
def _(m): return f"Not a damage report ({m[1]}) – forward to {_g(m[2])}."
@rule(r"^Keine Schadenmeldung – weiterleiten an (.*)$")
def _(m): return f"Not a damage report – forward to {_g(m[1])}"


# ---- reader / urgency / prior cases / tasks / warnings ---------------------------
@rule(r"^Regelmodus; gefundene Schlüsselwörter: (.*)\.$")
def _(m): return f"Rule mode; keywords found: {m[1]}."
@rule(r"^Regel-Untergrenze: (\w+); (.*?)(?:\. KI-Hinweis: (\w+); die strengere Einstufung gewinnt)?\.$")
def _(m):
    labels = "keine Dringlichkeitsregel getroffen" if m[2] == "keine Dringlichkeitsregel getroffen" else m[2]
    lab = "no urgency rule matched" if labels == "keine Dringlichkeitsregel getroffen" else ", ".join(_g(x) for x in labels.split(", "))
    hint = f". AI hint: {_g(m[3])}; the stricter level wins" if m[3] else ""
    return f"Rule minimum: {_g(m[1])}; {lab}{hint}."
@rule(r"^gleiche Einheit(.*)$")
def _(m):
    parts = ["same unit"]
    for p in [x.strip() for x in m[1].split(",") if x.strip()]:
        r = re.fullmatch(r"gleicher Raum \((.*)\)", p)
        if r: parts.append(f"same room ({_g(r[1])})")
        elif p == "verwandte Schadenart": parts.append("related type of damage")
        elif p == "kein erkennbarer fachlicher Zusammenhang": parts.append("no recognisable technical connection")
        else: return None
    return ", ".join(parts)
@rule(r"^Notfall-Regel greift – als Schadenmeldung behandelt, obwohl der Leser es anders eingestuft hat$")
def _(m): return "Emergency rule applies – treated as a damage report although the reader classified it differently"
@rule(r"^KI-Ausgabe ungültig – Regelmodus verwendet$")
def _(m): return "AI output invalid – rule mode used"
@rule(r"^KI-Dienst nicht erreichbar – Regelmodus verwendet$")
def _(m): return "AI service unreachable – rule mode used"
@rule(r"^KI-Limit erreicht \(429\) – Regelmodus verwendet$")
def _(m): return "AI rate limit reached (429) – rule mode used"
@rule(r"^Keine Aufzeichnung für diese E-Mail – Regelmodus verwendet$")
def _(m): return "No recording for this e-mail – rule mode used"
# task titles and checklist items (config/templates.yaml)
@rule(r"^(.+)-Handwerker beauftragen – (.*) \((\S+)\)$")
def _(m): return f"Commission {_g(m[1])} contractor – {' '.join(_g(w) for w in m[2].split())} ({m[3]})"
@rule(r"^Handwerker beauftragen – Ziel: (.*)$")
def _(m): return f"Commission contractor – target: {_template_translations().get(m[1], m[1])}"
@rule(r"^Erwähnte Fotos anfordern bzw\. beigefügte Fotos prüfen$")
def _(m): return "Request the mentioned photos or check attached photos"
@rule(r"^Hausmeister informieren$")
def _(m): return "Inform the caretaker"
@rule(r"^Zusammenhang mit '(.*)' \((\S+), erledigt durch (.*)\) prüfen – ggf\. Gewährleistung$")
def _(m): return f"Check connection with '{m[1]}' ({m[2]}, done by {m[3]}) – possibly a warranty case"
@rule(r"^Notdienst sofort beauftragen$")
def _(m): return "Commission emergency service immediately"
@rule(r"^Nachricht weiterleiten – (.*)$")
def _(m): return f"Forward message – {_g(m[1])}"
@rule(r"^Nachricht an (.*) zur Bearbeitung weiterleiten$")
def _(m): return f"Forward the message to {_g(m[1])} for processing"
@rule(r"^Technik / (.*)$")
def _(m): return f"technical team / {_g(m[1])}"
@rule(r"^Notfall im Gebäude bearbeiten – (.*?); Zuordnung klären: (.*)$")
def _(m): return f"Handle emergency in the building – {m[1]}; clarify assignment: " + _tr_list(m[2])
@rule(r"^Zuordnung klären – (.*?): (.*)$")
def _(m):
    where = "address unknown" if m[1] == "Adresse unbekannt" else m[1]
    return f"Clarify assignment – {where}: " + _tr_list(m[2])
@rule(r"^Zuordnung klären: (.*)$")
def _(m): return "Clarify assignment: " + _tr_list(m[1])
@rule(r"^Notfall im Gebäude bearbeiten – (.*?); Zuordnung klären: (.*)$")
def _(m): return f"Handle emergency in the building – {m[1]}; clarify assignment: " + _tr_list(m[2])
@rule(r"^Kandidaten und Zuordnungsgründe vergleichen$")
def _(m): return "Compare candidates and reasons"
@rule(r"^Vorbereitete Rückfrage an den Mieter nach Freigabe übermitteln$")
def _(m): return "After approval, send the prepared question to the tenant"
@rule(r"^Vertragsinhaber und Einheit klären; Entscheidung begründen und protokollieren$")
def _(m): return "Clarify contract holder and unit; justify and log the decision"
@rule(r"^Notdienst sofort zum Gebäude beauftragen$")
def _(m): return "Send emergency service to the building immediately"
@rule(r"^Hausmeister für das Gebäude informieren$")
def _(m): return "Inform the caretaker for the building"
@rule(r"^Betroffene Einheit und Vertragsinhaber klären$")
def _(m): return "Clarify the affected unit and contract holder"
@rule(r"^Trotz unbekannter Absenderadresse antworten$")
def _(m): return "Reply despite unknown sender address"
@rule(r"^Erneute Nachricht von registrierter E-Mail-Adresse erbitten$")
def _(m): return "Ask for a new message from the registered e-mail address"
@rule(r"^Mieter anrufen$")
def _(m): return "Call the tenant"


def translate(text: str | None) -> str | None:
    """English for a German system text, or None when unknown."""
    if not text:
        return None
    text = text.strip()
    if text in GLOSSARY:
        return GLOSSARY[text]
    tt = _template_translations()
    if text in tt:
        return tt[text]
    for pattern, fn in P:
        m = pattern.match(text)
        if m:
            out = fn(m)
            if out:
                return out
    return None


def translate_many(texts: list[str]) -> dict[str, str | None]:
    return {t: translate(t) for t in dict.fromkeys(texts)}
