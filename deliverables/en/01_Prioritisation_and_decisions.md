# Prioritisation and technical decisions

*English version of [../01_Priorisierung_und_Entscheidungen.md](../01_Priorisierung_und_Entscheidungen.md). The German document is the submitted original.*

## What mattered most to me

The task says: **an unclear assignment must never lead to an action on the wrong contract.** So I built the matching first and everything else afterwards. The data contains a trap: Max Mustermann has **two active contracts** at Musterstraße 12. Only "zweite Etage links" (second floor, left) decides – and the ERP writes it differently ("2. OG li.").

## The 9 steps by priority

| Step | Priority | Why |
|---|---|---|
| 4 ERP matching | **Must** | The actual test: wrong contract = wrong action. |
| 7 Structured record (JSON) | **Must** | Interface to ERP and workflow; makes every decision checkable. |
| 3 Extract information | **Must** | Without address and floor there is no safe matching; the side helps in addition. |
| 2 Recognise the type | **Must** | Damage or e.g. a rent question? Which trade? |
| 6 Urgency | **Must** | Water is running now – a wrong priority costs money. |
| 8 Reply draft | **Must** | Explicitly required – and never sent automatically. |
| 5 Earlier cases | Should | The earlier "Rohrverstopfung Küche" (blocked kitchen pipe) is an important hint for the contractor. |
| 9 Internal task | Should | Turns the result into work; a simple template is enough. |
| 1 Read the message | Should (simple) | Prototype: webhook/examples. A real mailbox is production work. |

**Deliberately not built:** real mailbox, real ERP interface, photo analysis, user roles. Not needed for a prototype; listed as next steps in the assessment.

## Technology – alternatives and decision

| Option | Strengths | Weaknesses | Decision |
|---|---|---|---|
| **Python service + n8n + own UI** | Logic testable (993 tests), rules in one file, n8n shows the process visibly | a bit more setup | **chosen** |
| n8n only | very visual, self-hostable | matching logic in code nodes is hard to test and version | n8n only as "glue" |
| LangChain / LangGraph | many building blocks | too heavy for 6 fixed steps, hides the simple logic | not needed |
| Dify | fast AI apps, built-in RAG | logic lives in platform settings, weak for fixed rules | better for the knowledge assistant |
| Streamlit UI | very fast | all Streamlit apps look alike, little control | not chosen |

**Core idea:** *The AI reads, fixed rules decide, a person acts.*

| Part | AI or rule? | Why |
|---|---|---|
| Recognise type, extract facts | AI (Groq); rules without a key | free language, also English |
| Assign contract, status | **fixed rules only** | must be repeatable, checkable and explainable – the AI never picks the contract |
| Urgency | rules as minimum + AI hint, the stricter level wins | safety: the AI may only raise it |
| Reply and task | text templates | a reply contains promises – wording must be approved by the business |

**AI provider:** Groq (free tier, model `openai/gpt-oss-120b`, strict JSON schema). If Groq returns invalid data, it is tried once more; if Groq is unreachable or at its limit, rule mode reads at once. The prototype runs **completely without a key**. Real Groq answers are recorded (`examples/llm_recorded/`) so anyone can follow them without a key.

## Handling uncertainty (the core)

1. **Points per signal:** name 0.30 · address 0.30 · floor 0.20 · side 0.10 · contact 0.10. Each signal: matches / partly / missing / contradicts – with a reason (German in the system, English in the UI's English mode).
2. **Contradiction = veto:** if the e-mail says "2. OG" and the contract is on the 3rd floor, that contract is out – whatever the threshold.
3. **Threshold (0.85) and gap (0.15):** the best contract must be good enough **and** clearly better than the second.
4. **Contract active?** Only once the unit is clear. If the contract has ended: review – **never** fall back to another contract.
5. **Additional review reasons:** name only similar, sender is not the contract holder, floor missing or unclear, English floor wording ("2nd floor" – British 2. OG, American 1. OG), several or uncertain locations (if the building itself is uncertain, no building-level action either).

Result: **"Please approve"**, **"Review needed"** or **"Forward"**. No status acts on its own. Every contract action needs an approval with name and time; for "review needed" also a reason. Everything is in the audit log.

For **emergencies** (gas, burst pipe): top of the list immediately, safety instructions in the reply – and **building-level** measures (emergency service, caretaker) are allowed even if the flat is still unclear (but not if the building is uncertain).

## Changing rules live

The business values live in `config/rules.yaml`. Example: set the threshold to 0.95 → save → in the review desk "Rules → Re-check all examples". The table shows immediately which cases change.

**Locally** the change applies as soon as the file is saved – no restart, no deployment. **Online** the app has to be redeployed after saving.
