# Overview – how to check the prototype

*English version of [../00_Uebersicht.md](../00_Uebersicht.md). Illustrated walk-through with screenshots (German): [../00_Rundgang.md](../00_Rundgang.md).*

**In short:** a tenant e-mail becomes a checked case in six steps. The AI reads the e-mail, fixed rules match it to the
right contract, a person approves. If anything is unclear, the system does not guess but says **"review needed"**.
Nothing is sent automatically.

## Access

| What | Link | Login |
|---|---|---|
| Review desk (UI) | https://inovidus-intake.onrender.com | user `demo`, password `demo` |
| n8n (visible process) | https://inovidus-n8n.onrender.com | `owner@intake-demo.example` / `Demo1234` |
| Source code | https://github.com/mithulram/inovidus-damage-intake | public |

Both services run on Render's free plan. After a longer pause they go to sleep: the first call of the review desk then
takes about a minute, n8n needs a few minutes to wake up. After that everything runs normally.

## A 5-minute walk-through
1. **Open the review desk**, choose the *Language* at the top right (Deutsch, English or both).
2. On the left open example **S1 "Wasserschaden Küche, Musterstraße 12"** – the e-mail from the task.
   Result: **MV-10245**, 0.90 points. MV-10487 is excluded because floor and side contradict.
   Below: earlier case "Rohrverstopfung Küche", urgency URGENT, reply draft, internal task, JSON.
3. Open **S2** (same e-mail without "zweite Etage links"): both contracts fit equally well → **review needed**,
   the draft asks the tenant. This is how uncertainty is handled.
4. Bottom left **"Check your own e-mail"**: type your own damage report and process it. At the top choose the *Reader*:
   "Rules (no AI)", "Groq · live" (AI reads live) or "Groq · recorded" (stored AI answers for five examples, e.g. S1 – works without a connection to Groq).
5. Tab **Rules**: the business values live in one file (`config/rules.yaml`). Running locally: change, save – applies at once, no deployment. Online version: change, save, then redeploy. Tab **Audit log**: every approval is
   recorded. Tab **Process**: the n8n workflow.

## Where to find what (your list from the task)

| Requested | File |
|---|---|
| Working prototype / workflow | links above · run locally: `README.md` ("In 3 Befehlen starten") |
| Workflow export / source code | `workflows/n8n_schadenmeldung.json` · source in `src/` |
| Example output | `examples/` (JSON of the task e-mail, with and without AI) |
| Architecture overview | `deliverables/en/02_Architecture.md` |
| What works, what not, risks, production | `deliverables/en/03_Assessment.md` |
| Reuse for a knowledge assistant | `deliverables/en/04_Reuse_knowledge_assistant.md` |
| AI usage and own checks | `deliverables/en/05_AI_usage.md` |
| Actual effort | `deliverables/en/06_Effort.md` |
| Tests and security | `deliverables/en/07_Tests_and_security.md` |
| Prioritisation and decisions | `deliverables/en/01_Prioritisation_and_decisions.md` |
