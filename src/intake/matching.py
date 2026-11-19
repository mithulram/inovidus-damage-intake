"""Step 4 – ERP matching with explicit uncertainty handling.

Two stages, four gates (see docs/PLAN.md §5.3):

Stage A – which contract/unit does the email describe?
  Active AND inactive contracts compete, so missing unit information can never hide an
  ambiguity between an inactive and an active unit.
  1. Vetoes: an explicit contradiction of address, floor or side removes a candidate.
  2. Threshold: best remaining score >= match.threshold.
  3. Margin: best - second best >= match.min_margin.
Stage B – may we act on it?
  4. Eligibility: the Stage-A winner must have an active contract. Never fall back.
Plus flags that force review independent of the score (identity, floor missing/unclear,
English floor counting, unknown sender if switched on).

Nothing here acts on a contract. The result is a proposal for a human.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from .erp import Contract, ERPConnector
from .models import (
    Candidate,
    Extraction,
    Flag,
    Gate,
    InboundEmail,
    MatchResult,
    NormalizedLocation,
    Signal,
)
from .normalize import compound_location, fold, normalize_house_no, normalize_location, normalize_street
from .rules import Rules

SIDE_LABEL = {"L": "links", "R": "rechts", "M": "Mitte"}


def _name_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return float(fuzz.token_sort_ratio(fold(a), fold(b)))


def _digits(phone: str | None) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())[-9:]


def _floor_text(floor: int | None) -> str:
    if floor is None:
        return "–"
    return "EG" if floor == 0 else f"{floor}. OG"


def _score_contract(
    contract: Contract,
    ext: Extraction,
    loc: NormalizedLocation,
    email: InboundEmail,
    rules: Rules,
) -> Candidate:
    w = rules.match.weights
    m = rules.match
    signals: list[Signal] = []
    vetoes: list[str] = []
    veto_gates: list[Gate] = []

    # --- name -------------------------------------------------------------
    named = ext.tenant_name or ext.sender_name
    sim = _name_similarity(named, contract.tenant_name)
    if not named:
        signals.append(Signal(name="name", result="missing", weight=w.name, points=0, erp_value=contract.tenant_name,
                              reason="Kein Name in der Nachricht"))
    elif sim >= m.name_full_min:
        signals.append(Signal(name="name", result="match", weight=w.name, points=w.name, email_value=named,
                              erp_value=contract.tenant_name, reason=f"Name stimmt überein ({sim:.0f} %)"))
    elif sim >= m.name_partial_min:
        signals.append(Signal(name="name", result="partial", weight=w.name, points=round(w.name / 2, 4), email_value=named,
                              erp_value=contract.tenant_name, reason=f"Name ähnlich, aber nicht gleich ({sim:.0f} %)"))
    else:
        signals.append(Signal(name="name", result="mismatch", weight=w.name, points=0, email_value=named,
                              erp_value=contract.tenant_name, reason=f"Anderer Name ({sim:.0f} %)"))

    # --- address (street + house number) ----------------------------------
    erp_addr = f"{contract.street} {contract.house_no}"
    if not loc.street and not loc.house_no:
        signals.append(Signal(name="address", result="missing", weight=w.address, points=0, erp_value=erp_addr,
                              reason="Keine Adresse in der Nachricht"))
    else:
        street_ok = loc.street is None or loc.street == normalize_street(contract.street)
        house_ok = loc.house_no is None or loc.house_no == normalize_house_no(contract.house_no)
        email_addr = f"{ext.street_raw or '?'} {ext.house_no or '?'}"
        if street_ok and house_ok and loc.street and loc.house_no:
            signals.append(Signal(name="address", result="match", weight=w.address, points=w.address, email_value=email_addr,
                                  erp_value=erp_addr, reason=f"Adresse stimmt überein ('{email_addr}' = '{erp_addr}')"))
        elif street_ok and house_ok:
            # Plan §5.2: the address counts only as street + number; incomplete = missing (0 points, no veto).
            missing_part = "Hausnummer" if not loc.house_no else "Straße"
            signals.append(Signal(name="address", result="missing", weight=w.address, points=0,
                                  email_value=email_addr, erp_value=erp_addr,
                                  reason=f"Adresse unvollständig ({missing_part} fehlt) – zählt nicht"))
        else:
            what = "Straße" if not street_ok else "Hausnummer"
            msg = f"Adresse widerspricht: {what} ('{email_addr}' ≠ '{erp_addr}')"
            signals.append(Signal(name="address", result="mismatch", weight=w.address, points=0, email_value=email_addr,
                                  erp_value=erp_addr, reason=msg))
            vetoes.append(msg)
            veto_gates.append(Gate.VETO_ADDRESS)

    # --- floor ------------------------------------------------------------
    erp_floor = contract.floor_label
    if loc.floor is None:
        reason = loc.floor_note or "Keine Etage angegeben"
        signals.append(Signal(name="floor", result="missing", weight=w.floor, points=0, email_value=ext.floor_raw,
                              erp_value=erp_floor, reason=reason))
    elif loc.floor == contract.floor:
        signals.append(Signal(name="floor", result="match", weight=w.floor, points=w.floor, email_value=ext.floor_raw,
                              erp_value=erp_floor, reason=f"'{ext.floor_raw}' = {erp_floor}"))
    else:
        msg = f"Etage widerspricht: {_floor_text(loc.floor)} ≠ {erp_floor}"
        signals.append(Signal(name="floor", result="mismatch", weight=w.floor, points=0, email_value=ext.floor_raw,
                              erp_value=erp_floor, reason=msg))
        vetoes.append(msg)
        veto_gates.append(Gate.VETO_UNIT)

    # --- side -------------------------------------------------------------
    erp_side = contract.side_label
    if loc.side is None:
        signals.append(Signal(name="side", result="missing", weight=w.side, points=0, email_value=ext.side_raw,
                              erp_value=erp_side, reason="Keine Seite (links/rechts) angegeben"))
    elif loc.side == contract.side:
        signals.append(Signal(name="side", result="match", weight=w.side, points=w.side, email_value=ext.side_raw,
                              erp_value=erp_side, reason=f"'{ext.side_raw}' = {erp_side}"))
    else:
        msg = f"Seite widerspricht: {SIDE_LABEL[loc.side]} ≠ {erp_side}"
        signals.append(Signal(name="side", result="mismatch", weight=w.side, points=0, email_value=ext.side_raw,
                              erp_value=erp_side, reason=msg))
        vetoes.append(msg)
        if Gate.VETO_UNIT not in veto_gates:
            veto_gates.append(Gate.VETO_UNIT)

    # --- contact (sender email / phone) -------------------------------------
    erp_email = (contract.contact.email or "").lower() or None
    erp_phone = _digits(contract.contact.phone)
    sender = (email.sender_email or "").lower() or None
    phone = _digits(ext.phone)
    if sender and erp_email and sender == erp_email:
        signals.append(Signal(name="contact", result="match", weight=w.contact, points=w.contact, email_value=sender,
                              erp_value=erp_email, reason="Absenderadresse ist im ERP hinterlegt"))
    elif phone and erp_phone and phone == erp_phone:
        signals.append(Signal(name="contact", result="match", weight=w.contact, points=w.contact, email_value=ext.phone,
                              erp_value=contract.contact.phone, reason="Telefonnummer ist im ERP hinterlegt"))
    elif sender:
        # Present but unknown = missing, not a contradiction (tenants write from private addresses).
        signals.append(Signal(name="contact", result="missing", weight=w.contact, points=0, email_value=sender,
                              erp_value=erp_email, reason="Absenderadresse nicht im ERP hinterlegt"))
    else:
        signals.append(Signal(name="contact", result="missing", weight=w.contact, points=0, erp_value=erp_email,
                              reason="Keine Absenderadresse vorhanden"))

    score = round(sum(s.points for s in signals), 4)
    return Candidate(
        contract_id=contract.contract_id,
        tenant_name=contract.tenant_name,
        unit_label=contract.unit_label,
        object_id=contract.object_id,
        unit_id=contract.unit_id,
        active=contract.active,
        score=score,
        signals=signals,
        vetoes=vetoes,
        veto_gates=veto_gates,
    )


def ext_contact_email(candidate: Candidate, erp: ERPConnector) -> str | None:
    contract = erp.contract(candidate.contract_id)
    if contract is None or not contract.contact.email:
        return None
    return contract.contact.email.strip().lower()


def _is_candidate(contract: Contract, ext: Extraction, loc: NormalizedLocation, rules: Rules) -> bool:
    named = ext.tenant_name or ext.sender_name
    if named and _name_similarity(named, contract.tenant_name) >= rules.match.candidate_name_min:
        return True
    if loc.street and loc.house_no:
        return loc.street == normalize_street(contract.street) and loc.house_no == normalize_house_no(contract.house_no)
    return False


def _address_certain(loc: NormalizedLocation, erp: ERPConnector) -> str | None:
    """Return the object_id if street + house number identify exactly one building."""
    if not (loc.street and loc.house_no):
        return None
    hits = [p.object_id for p in erp.properties()
            if normalize_street(p.street) == loc.street and normalize_house_no(p.house_no) == loc.house_no]
    return hits[0] if len(hits) == 1 else None


def match(ext: Extraction, email: InboundEmail, erp: ERPConnector, rules: Rules) -> MatchResult:
    loc = normalize_location(ext.street_raw, ext.house_no, ext.floor_raw, ext.side_raw, rules.normalize)
    contracts = [c for c in erp.contracts() if _is_candidate(c, ext, loc, rules)]
    candidates = sorted((_score_contract(c, ext, loc, email, rules) for c in contracts),
                        key=lambda c: (-c.score, c.contract_id))
    object_id = _address_certain(loc, erp)
    failed: list[Gate] = []
    flags: list[Flag] = []

    def fail(gate: Gate, message: str) -> None:
        if gate not in failed:
            failed.append(gate)
        flags.append(Flag(gate=gate, message=message))

    # Flags about the email itself (independent of any score) ---------------
    if loc.floor_status in ("missing", "unclear"):
        fail(Gate.FLOOR_MISSING, loc.floor_note or "Etage fehlt oder ist unklar – beim Mieter nachfragen")
    if loc.floor_status == "english_ordinal" and rules.normalize.english_floor_counting == "ask":
        fail(Gate.FLOOR_AMBIGUOUS, f"Zählweise der Etage unklar: {loc.floor_note}")
    building_uncertain = False
    # Same check for every provider: a single field that itself holds alternatives is ambiguous too.
    field_values = {"street": ext.street_raw, "house_no": ext.house_no, "floor": ext.floor_raw, "side": ext.side_raw}
    compound = {f: v for f, v in field_values.items() if compound_location(v, f, rules.normalize)}
    alternatives = list(dict.fromkeys([*ext.location_alternatives, *compound.values()]))
    if compound.keys() & {"street", "house_no"}:
        building_uncertain = True
        object_id = None
    if alternatives:
        fail(Gate.UNIT_AMBIGUOUS, "E-Mail nennt mehrere oder unsichere Ortsangaben: "
                                  + "; ".join(alternatives) + " – beim Mieter nachfragen")
        street_word = re.compile(
            r"(str\.?|stra(ss|ß)e|weg|platz|allee|gasse|ring)(\b|\d)|\b\d+\s*[a-z]?\s*$"
            r"|adresse|anschrift|hausnummer|hausnr|haus\b|gebäude|gebaeude|objekt"
            r"|address|house|street|building",
            re.IGNORECASE)
        unit_word = re.compile(r"\b(og|eg|dg|ug|etage|stock|stockwerk|geschoss|floor|links|rechts|li\.?|re\.?|mitte|left|right)\b",
                               re.IGNORECASE)
        # Fail-safe: doubt counts as doubt about the BUILDING unless it clearly concerns only floor/side.
        bare_floor = re.compile(r"^\s*\d+\s*\.?\s*$")  # "2." from "2. oder 3. OG"
        building_uncertain = building_uncertain or any(street_word.search(alt) or not (unit_word.search(alt) or bare_floor.match(alt))
                                 for alt in ext.location_alternatives)
        if building_uncertain:
            object_id = None

    # Stage A ---------------------------------------------------------------
    valid = [c for c in candidates if not c.vetoes]
    winner: Candidate | None = None
    margin: float | None = None
    if not candidates:
        fail(Gate.NO_CANDIDATE, "Kein passender Vertrag im ERP gefunden")
    elif not valid:
        top = candidates[0]
        for gate in top.veto_gates:
            fail(gate, f"{top.contract_id}: " + "; ".join(top.vetoes))
    else:
        # Vetoed candidates stay visible with their reasons but do not block a valid winner.
        winner = valid[0]
        second = valid[1].score if len(valid) > 1 else 0.0
        margin = round(winner.score - second, 4)
        if winner.score < rules.match.threshold:
            fail(Gate.THRESHOLD, f"Beste Übereinstimmung {winner.score:.2f} liegt unter der Schwelle {rules.match.threshold:.2f}")
        if margin < rules.match.min_margin:
            rival = (f"{winner.contract_id} und {valid[1].contract_id} kommen in Frage" if len(valid) > 1
                     else f"nur {winner.contract_id} übrig, aber Abstand zu 0 reicht nicht")
            fail(Gate.MARGIN, f"Abstand zum Zweitbesten nur {margin:.2f} (mindestens {rules.match.min_margin:.2f}) – {rival}")

    # Identity flags (on the Stage-A winner) ---------------------------------
    unknown_sender = False
    if winner is not None:
        name_sig = next(s for s in winner.signals if s.name == "name")
        if name_sig.result == "partial":
            fail(Gate.IDENTITY, f"Name weicht ab: '{name_sig.email_value}' vs. '{winner.tenant_name}'")
        if ext.sender_name and _name_similarity(ext.sender_name, winner.tenant_name) < rules.match.name_full_min \
                and name_sig.result != "partial":
            fail(Gate.IDENTITY, f"Absender '{ext.sender_name}' ist nicht Vertragsinhaber ({winner.tenant_name})")
        # Unknown sender is about the e-mail address only – a matching phone number earns points
        # but does not make an unregistered address "registered".
        sender = (email.sender_email or "").strip().lower()
        unknown_sender = bool(sender) and sender != ext_contact_email(winner, erp)
        if unknown_sender and rules.match.unknown_sender_forces_review:
            fail(Gate.IDENTITY, "Nachricht nicht von der registrierten E-Mail-Adresse")

    # Stage B – eligibility (only when Stage A identified exactly one unit) ---
    stage_a_ok = winner is not None and not ({Gate.THRESHOLD, Gate.MARGIN} & set(failed))
    if stage_a_ok and not winner.active:
        fail(Gate.ELIGIBILITY, f"Einheit erkannt ({winner.unit_label}), aber Vertrag {winner.contract_id} ist "
                               f"inaktiv – Mieterwechsel/Leerstand prüfen. Kein Ausweichen auf einen anderen Vertrag.")

    selected = winner.contract_id if (winner is not None and not failed) else None
    if selected:
        reason = (f"Eindeutig: {winner.contract_id} ({winner.unit_label}) mit {winner.score:.2f} Punkten, "
                  f"Abstand {margin:.2f}. Bitte prüfen und freigeben.")
    else:
        reason = "Prüfung nötig: " + " | ".join(f.message for f in flags)
    return MatchResult(
        location=loc,
        candidates=candidates,
        winner=winner.contract_id if winner else None,
        selected_contract=selected,
        score=winner.score if winner else None,
        margin=margin,
        failed_gates=failed,
        flags=flags,
        object_id=object_id,
        unknown_sender=unknown_sender,
        building_uncertain=building_uncertain,
        reason=reason,
    )
