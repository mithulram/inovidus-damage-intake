# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

delegated: plain HTML/CSS + small vanilla JS served as static files by the project's FastAPI app (same process as the JSON API). No build step, no framework, no CDN – it must run offline on a reviewer's laptop with `uv run intake-ui`. Chosen by Claude; Mithul delegated the decision ("whatever you think is best") and rejected Streamlit's generic look.

## Users

- **Primary – the Sachbearbeiter (case worker) at a German property-management company.** Works through incoming tenant emails at a desk, often with a phone call coming in; must decide quickly which contract/unit a damage report belongs to, how urgent it is, and approve a reply and a craftsman order. Not a programmer.
- **Evaluating audience – Inovidus GmbH** (ERP/system-integration and AI consultancy for Immobilienwirtschaft and insurance): the managing director and a colleague watch Mithul share his screen in a Teams interview, change business rules live, and judge whether a non-programmer can follow every decision. (Confirmed: task brief and Mithul.)

## Product Purpose

Turn one tenant email into a checked, explainable case: what happened, which contract/unit it belongs to and how sure we are, how urgent it is, what earlier cases exist, a reply draft and an internal task. Success = the right case gets prepared in seconds and an unclear case is never acted on without a human decision. Nothing is ever sent or written to the ERP automatically.

## Positioning

The interface makes **uncertainty visible and decidable**: every candidate contract shows its points per signal (name, address, floor, side, contact) with a German reason, contradictions shown as vetoes, and the exact rule that stopped automation (threshold, margin, inactive contract, identity, missing floor). A generic "AI inbox" shows one confident answer; this one shows why, and where it refuses to guess.

## Operating Context

- Input: tenant emails (German, sometimes English). Demo inbox = 14 scenario emails plus free paste; production would be a mailbox/n8n webhook.
- ERP terms the users know: Mietvertrag (MV-…), Objekt, Einheit, Etage (EG, 1. OG, 2. OG …, German counting), links/rechts, Vorgang, Hausmeister, Handwerker, Gewerk.
- Statuses: "bitte freigeben" (ready for approval), "Prüfung nötig" (needs review), "kein Schadensfall – weiterleiten". Urgency: NOTFALL / DRINGEND / NORMAL with response targets.
- Actions are only possible through approval (assignment, contractor order, building-level action, reply approval for copying, staff option for unknown senders). An audit log records every action.
- The business rules live in `config/rules.yaml`; the UI shows them read-only so they can be changed live and re-run.
- Used on a laptop or external monitor during screen sharing (1280–1920 px wide); must stay legible when the video stream compresses it.

## Capabilities and Constraints

- API: `/api/scenarios`, `/api/process`, `/api/steps/{name}`, `/api/cases`, `/api/approve`, `/api/rules`, `/api/audit`, `/api/cases/{id}/reply?variant=`.
- Providers: offline rules (default, no key), Groq (`openai/gpt-oss-120b`), recorded Groq responses. The UI shows which one read the email.
- No send button may exist anywhere. Reply approval = "freigeben & kopieren".
- German UI labels; English only for technical terms where German is unusual.
- Undecided: nothing material.

## Brand Commitments

None. Inovidus's own brand is not to be imitated. The product is an anonymous internal tool ("Hausverwaltung" as generic sender). (Inferred: no brand assets were provided.)

## Evidence on Hand

- Synthetic ERP data (`data/erp_contracts.json`, `data/cases.json`) – task data plus clearly marked synthetic contacts and distractor contracts.
- 14 scenario emails with expected outcomes (`scenarios/*.yaml`); 5 real recorded Groq responses (`examples/llm_recorded/`).
- No customers, metrics, testimonials or real tenant data exist; none may be invented.

## Product Principles

1. Show the reason next to every decision – a non-programmer must be able to read why.
2. Uncertainty is a state, not an error: "Prüfung nötig" is a first-class, calm, well-designed outcome.
3. Humans act, the system prepares: approval is explicit, logged, and never implied.
4. Emergencies jump the queue even when the unit is unclear.
5. One email, one screen: the whole path from email to decision is visible without hunting.

## Accessibility & Inclusion

WCAG 2.2 AA contrast; full keyboard operation; status never conveyed by colour alone (text label + icon shape); legible at 125 % zoom and through video compression (no thin hairline text, minimum 14 px UI text).
