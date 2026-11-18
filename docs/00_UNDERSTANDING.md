# 00 – What this task is really about

## What Inovidus grades
The email says it plainly: *not* a perfect or production-ready solution. They grade:
1. **Prioritisation** – which of the 9 steps get built first, and why. Saying "I left X out because Y" is part of the answer.
2. **Technical decisions** – a tech choice with reasons and trade-offs, not just "I used tool X".
3. **Business process → traceable solution** – a non-programmer must be able to follow every step: input → what the system decided → why.
4. **Handling uncertainty** – the one thing they call out as "insbesondere wichtig". An unclear match must never trigger an action on the wrong contract or property.
5. **Communication** – in the interview they change rules live and want explanations a business person understands.

## The trap in the data
- "Max Mustermann" has **two active contracts at the same address** (Musterstraße 12): MV-10245 (2. OG li.) and MV-10487 (3. OG rechts).
- Name + address alone → a tie. Only the unit hint **"zweite Etage links"** separates them, and it is written differently from the ERP ("zweite Etage" ↔ "2. OG", "links" ↔ "li.", "Musterstr." ↔ "Musterstraße"). So normalisation is required, not a plain string compare.
- MV-10245 has a **closed case "Rohrverstopfung Küche"**. A pipe blockage in the same kitchen followed by water under the sink is a plausible **recurrence / related cause**. It belongs in the internal task (craftsman should check the connection), not in the tenant reply.
- Hidden second-order traps: the email has no sender address or phone number given in the task; "Fotos sind vorhanden" means photos are **not attached** → request them; "seit gestern" = ongoing leak → urgency is high but this is not a classic emergency (no flooding, no gas, no electrical risk mentioned). "Bitte dringend" is the tenant's wish, not proof of urgency – the system should reason from facts.

## What Inovidus builds (research, ~10 min, inovidus.de)
- Based in Kemnath. Three service lines: **ERP & system integration** (ERP ↔ DMS, CAFM, portal, reporting, workflow), **transformation / project management**, **AI solutions & AI agents** ("Wissen und Dokumente nutzbar machen", "KI in bestehende Systeme und Prozesse integrieren").
- Industry focus: **Immobilienwirtschaft** and **Versicherungswesen**, Mittelstand and Konzerne.
- The website names **no concrete tools** (no n8n, Dify, LangChain, no ERP vendor, no LLM, no hosting statement). Hence: don't bet on one tool. Pick something transparent and testable, and show it can plug into a workflow engine (n8n is common in German property-management automation, self-hostable, EU-friendly).
- Implication: their clients care about **ERP integration, DSGVO, audit trail, and staff relief** – the plan should speak that language (connector interface for the ERP, human approval, EU hosting).

## What they may change live in the interview – and how to stay flexible
Likely changes: unit not mentioned; contract inactive / tenant moved out; new tenant not in ERP; name spelled differently or unknown sender; a real emergency (burst pipe, gas); a non-damage message (rent question); English email; a different threshold ("only auto-assign above 95 %"); new urgency rule ("no heating in winter = Notfall"); new damage category; different response times.

Design consequences:
- **All business rules in one config file** (YAML): thresholds, margin, signal weights, urgency keywords → levels, response times, damage categories, task templates. A live change = edit one line, re-run.
- **ERP and cases as plain JSON seed files** → toggle a contract to inactive or add a tenant in seconds.
- **Scenario suite** as data files with expected outcomes, runnable with one command and visible in the UI.
- **Every decision carries a reason string** in German, so the screen itself explains the result to a non-programmer.
- **Runs without an API key** (rule-based mode), so a live change never depends on network or quota.
