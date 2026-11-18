---
version: 1
slug: "src-intake-web-static-index-html"
primary_target: "src/intake/web/static/index.html"
related_targets: []
---

# Surface: Sachbearbeiter-Arbeitsplatz (src/intake/web/static/index.html)

Mode: Operate. Audience: case worker at a German Hausverwaltung; evaluated live by Inovidus over screen share. Job: take one tenant email from inbox to an approved, explained decision. Proof: real scenario emails, candidate scores with German reasons, gate that stopped automation, audit log. Constraints: no send button, offline, no CDN, German labels, WCAG AA, legible through video compression.
Substitution: Impeccable's interview/decision page was not served – Mithul explicitly delegated all design decisions in chat ("you know better", "whatever you want"); directions were weighed unattended and the assigned direction built.

## Direction contract
THESIS: A case is a Durchschreibesatz – one decision written once and carried through three tinted copies (Antwort an Mieter, Auftrag, Aktenvermerk). It refuses the category default of a grey SaaS inbox with one blue accent and a confident single answer.
OWN-WORLD: Copy-paper tints – white top sheet, canary second copy, rose third copy – on a cool grey-blue desk ground; carbon-blue ink (#1f3a8a family) for everything the system or a human "wrote"; Vordruck red-brown for preprinted labels and rules; one signal vermilion reserved for NOTFALL only, held until handled. Barlow (DIN-like grotesk, self-hosted) in Regular/Medium/SemiBold, Semi Condensed for preprinted field labels, tabular figures for scores. Perforation as the only ornament: a dashed tear line between sheets.
STORY: The visitor sees which email, what the system read, which flat in the building it points to and how sure it is, why it stopped or not, then approves – and sees the approval stamped onto the copies.
FIRST VIEWPORT: Left rail = Posteingang ranked by urgency (NOTFALL rows pinned, vermilion edge mark + label), each row: Betreff, Absender, Status label. Main = the open case as a form: header strip (Vorgangsnummer, Eingang, Leser: Regeln/Groq); row 1 original email (left) beside "Erkannt" fields; row 2 Zuordnung: candidate table (points per signal ✔ / ½ / – / ✖, veto hatched) next to the Hausraster (building grid EG–3. OG × links/rechts; winner outlined in carbon blue, vetoed units hatched, inactive struck); row 3 the gate verdict line in plain German. Bottom = the Durchschreibesatz: three offset sheets with tabs; primary action "Zuordnung freigeben" isolated at the right with empty space around it.
FORM: Durchschreibesatz (carbon-copy order pad), position 7 of 7 on my grounded list; raised by: building grid ↔ candidate linking (from doujin catalog's cell↔hall-map), urgency-ranked inbox with one held alert colour (gate board), veto shown by hatch not colour alone (exposure record), isolated approval actions (developer console). seed: seed:5a1c6da4ecea088c
SIGNATURE: Approving writes a carbon-blue Paraphe stamp (Name, Uhrzeit, "freigegeben") that appears on all three sheets at once – the visible "Durchschlag"; only then does "Kopieren" activate on the reply sheet. Hovering a candidate row lights its flat in the Hausraster and vice versa.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
