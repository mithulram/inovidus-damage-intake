"""German → English for every text the system generates (reasons, gates, warnings, tasks, rules).

Business language stays German (reply drafts follow the tenant's language). In the UI's English
mode each German text is shown with its English translation. Translation is deterministic: ordered
sentence patterns plus a small glossary – no LLM, so it works offline and never invents content.
Unknown text returns None (the UI then shows the German original only).
"""

from __future__ import annotations

import re
from functools import lru_cache

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


_FIELD_EN = {"Straße": "street", "Hausnummer": "house number", "Etage": "floor", "Seite": "side"}


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
@rule(r"^PLZ/Ort '(.*)' passt nicht zu (.*) – beim Mieter nachfragen$")
def _(m): return f"Postcode/town '{m[1]}' does not match {m[2]} – ask the tenant"
@rule(r"^Absender schreibt für eine andere Person \('(.*)'\) – Vertragsinhaber klären$")
def _(m): return f"Sender writes for another person ('{m[1]}') – confirm the contract holder"
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
def _(m):
    words = [w.strip() for w in m[1].split(",")]
    if words == ["keine"]:
        return "Rule mode; keywords found: none."
    return "Rule mode; keywords found: " + ", ".join(
        f"{w} ({KEYWORDS_EN[w]})" if KEYWORDS_EN.get(w) and KEYWORDS_EN[w] != w else w for w in words) + "."
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
@rule(r"^KI-Angabe nicht im Text gefunden, nicht verwendet: (\w+) '(.*)'$")
def _(m): return f"AI value not found in the e-mail, not used: {_FIELD_EN.get(m[1], m[1])} '{m[2]}'"
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
    ph = example_translations()["phrases"]
    if text in ph:
        return ph[text]
    for pattern, fn in P:
        m = pattern.match(text)
        if m:
            out = fn(m)
            if out:
                return out
    return None


def translate_many(texts: list[str]) -> dict[str, str | None]:
    return {t: translate(t) for t in dict.fromkeys(texts)}


# ---- keywords, example e-mails and the rules file (reading aids for the English UI) -----
KEYWORDS_EN: dict[str, str] = {
    "schaden": "damage", "wasser": "water", "undicht": "leaking", "kaputt": "broken", "defekt": "defective",
    "leck": "leak", "tropft": "drips", "rohr": "pipe", "schimmel": "mould", "heizung": "heating", "gas": "gas",
    "strom": "power", "ausfall": "failure", "verstopf": "blocked", "wasserschaden": "water damage",
    "spüle": "sink", "waschbecken": "washbasin", "aufgequollen": "swollen", "feucht": "damp",
    "läuft wasser": "water running", "wasser läuft": "water running", "wasser unter": "water under",
    "läuft aus der": "leaking from the", "läuft aus dem": "leaking from the", "rohrbruch": "burst pipe",
    "rohr geplatzt": "pipe burst", "wasser kommt durch die decke": "water through the ceiling",
    "durch die decke": "through the ceiling", "verstopft": "blocked", "verstopfung": "blockage",
    "rohrverstopfung": "blocked pipe", "läuft nicht ab": "not draining", "abfluss": "drain",
    "heizungsausfall": "heating failure", "kein warmwasser": "no hot water", "kalt": "cold",
    "heizung ausgefallen": "heating failed", "heizung geht nicht": "heating not working",
    "keine heizung": "no heating", "gasgeruch": "gas smell", "riecht nach gas": "smells of gas",
    "fenster": "window", "tür": "door", "schloss": "lock", "küche": "kitchen", "bad": "bathroom",
    "badezimmer": "bathroom", "schlafzimmer": "bedroom", "wohnzimmer": "living room", "flur": "hallway",
    "keller": "basement", "balkon": "balcony", "treppenhaus": "stairwell", "miete": "rent",
    "mieterhöhung": "rent increase", "lastschrift": "direct debit", "nebenkosten": "service charges",
    "kaution": "deposit", "kurzschluss": "short circuit", "stromausfall": "power outage",
    "tritt aus": "escaping", "läuft unter": "running under", "durchfeuchtet": "soaked",
    "feuchte wand": "damp wall", "überschwemm": "flood", "wasser steht": "standing water",
    "dringend": "urgent", "sofort": "immediately", "schnellstmöglich": "as soon as possible", "eilig": "urgent",
}

_RULES_COMMENTS_EN: dict[str, str] = {
    "Geschäftsregeln – die EINZIGE Stelle, an der fachliche Regeln stehen.": "Business rules – the ONLY place where business rules live.",
    "Eine Regel ändern = eine Zeile hier ändern und neu ausführen.": "Changing a rule = change one line here and run again.",
    "(Secrets und Anbieter-Auswahl stehen in .env, nicht hier.)": "(Secrets and the AI provider choice live in .env, not here.)",
    "1) Zuordnung zum ERP (Mieter / Objekt / Einheit)": "1) Matching to the ERP (tenant / building / unit)",
    "Mindestpunktzahl des besten Kandidaten (0..1)": "minimum score of the best candidate (0..1)",
    "Mindestabstand zum Zweitbesten": "minimum gap to the second best",
    "ab dieser Namensähnlichkeit (0..100) wird ein Vertrag überhaupt Kandidat": "from this name similarity (0..100) a contract becomes a candidate at all",
    "ab hier zählt der Name voll": "from here the name counts in full",
    'zwischen partial und full: halbe Punkte + "Name weicht ab" (Prüfung nötig)': 'between partial and full: half points + "name differs" (review needed)',
    "Summe = 1.0": "sum = 1.0",
    "true = Mail von unbekannter Adresse immer prüfen lassen": "true = always review e-mails from an unknown address",
    "2) Normalisierung (deutsche Zählweise: EG = Erdgeschoss, 1. OG = erste Etage)": "2) Normalisation (German counting: EG = ground floor, 1. OG = first floor above ground)",
    'ask = "2nd floor" zählt als 2. OG, aber Rückfrage nötig | european = ohne Rückfrage': 'ask = "2nd floor" counts as 2. OG, but the tenant is asked | european = no question',
    "Zahlwörter -> Etage": "number words -> floor",
    'Gebäudeteile: allein ("Hinterhaus") oder mit Kennung ("Haus B", "Aufgang 2") -> Gebäude unklar -> Prüfung': 'building parts: alone ("Hinterhaus" = rear building) or with a label ("Haus B", "Aufgang 2") -> building unclear -> review',
    "3) Art der Nachricht und Schadenart": "3) Type of message and type of damage",
    "keine Schadenmeldung -> weiterleiten, keine Schadenaufgabe": "not a damage report -> forward, no damage task",
    "Reihenfolge = Priorität bei mehreren Treffern": "order = priority when several match",
    "4) Dringlichkeit – Regeln setzen die UNTERGRENZE; die KI darf nur erhöhen": "4) Urgency – rules set the MINIMUM; the AI may only raise it",
    "erste passende Regel je Stufe zählt; die höchste Stufe gewinnt": "first matching rule per level counts; the highest level wins",
    "Schadenart (auch von der KI erkannt) -> Sicherheitshinweise bei NOTFALL": "damage type (also recognised by the AI) -> safety instructions for EMERGENCY",
    "Gas: keine Hinweise, die Schalter oder Sicherungen betätigen lassen": "gas: no instructions that make people use switches or fuses",
    "5) Bestehende Vorgänge": "5) Existing cases",
    "Schadenart -> verwandte frühere Vorgänge": "damage type -> related earlier cases",
}
_VALUE_KEYS = ("name", "trade", "label", "route_to")


@lru_cache(maxsize=1)
def example_translations() -> dict:
    path = ROOT / "config" / "i18n" / "examples_en.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {"scenarios": data.get("scenarios") or {}, "phrases": data.get("phrases") or {}}


def rules_yaml_en(raw: str) -> str:
    """The rules file with English comments; German values that the system matches or outputs keep their
    German text and get the English meaning appended as a comment. The real file is never changed."""
    out = []
    for line in raw.split("\n"):
        code, sep, comment = line.partition("#")
        if sep and comment.strip() in _RULES_COMMENTS_EN:
            line = f"{code}# {_RULES_COMMENTS_EN[comment.strip()]}"
        elif not sep:
            m = re.match(r'^(\s*-?\s*(?:%s):\s*)(.+?)\s*$' % "|".join(_VALUE_KEYS), line)
            q = re.match(r'^(\s*-\s*)"(.+)"\s*$', line)
            rt = re.search(r'response_target: "([^"]+)"', line)
            if m and (en := translate(m[2])) and en != m[2]:
                line = f"{line}   # = {en}"
            elif q and (en := translate(q[2])):
                line = f"{line}   # = {en}"
            elif rt and (en := translate(rt[1])):
                line = f"{line}   # = {en}"
        out.append(line)
    return "\n".join(out)
