# Assessment: what works, what doesn't yet, risks, production

*English version of [../03_Einschaetzung.md](../03_Einschaetzung.md).*

## What already works

- The original e-mail is assigned to **MV-10245** (0.90 points). MV-10487 is excluded with a reason ("floor contradicts: 2. OG ≠ 3. OG").
- The earlier "Rohrverstopfung Küche" is recognised as a **possible connection** and goes into the internal task – not into the reply to the tenant.
- **14 scenarios** run automatically (e.g. no floor, inactive contract, other sender, gas emergency, rent question, English, lowered threshold). All behave as expected. 993 automated tests in total.
- Runs without an API key (rule mode) and with Groq (live or recorded).
- n8n workflow with one node per step, actually executed; the result lands in the review list.
- Case-worker UI in German and English: reasons, building grid, approval with stamp, audit log. **There is no send button.**

## What does not work reliably yet

- The **rule mode without AI** only recognises known wording (keywords). Unusual sentences are recognised less well → more often "review needed", not a wrong assignment.
- **Groq** gives good results in the tested cases, but only 5 cases are recorded. A quality statement needs a larger test set of real (anonymised) e-mails.
- **Identity:** an e-mail does not prove who writes. The prototype warns about an unknown sender address; a person decides.
- **Time expressions** ("since yesterday") are kept as text, not converted into a date.
- **Photos/attachments** are not analysed.
- The reply texts are templates; correct, but not yet approved by a business department.
- English translation of system texts is deterministic; AI free text (Groq's own reasoning) stays German and is labelled as such.

## Risks

| Risk | How the prototype handles it | What production adds |
|---|---|---|
| Wrong contract | veto, threshold, gap, active check, human approval | measure how often people change the proposal |
| AI invents data | AI only copies text spans; rules convert; schema check; failure → rule mode | regular test set, monitoring |
| Emergency left lying | emergency on top, safety advice, building action allowed without unit | 24/7 on-call, SMS/phone; possibly an approved automatic receipt |
| Data protection (GDPR) | synthetic test data (plus one own test tenant); only the e-mail text goes to the AI, never ERP data | EU hosting or a data processing agreement, deletion periods, roles |
| Groq is a US provider, free tier | demo only | EU model (e.g. Azure OpenAI EU, Mistral) or self-hosted |
| Reply with a wrong promise | templates instead of free AI text; never sent automatically | business approves templates |
| Public demo link | password-protected hosting (see README) | login and roles |

## What production still needs

1. **Mailbox connection** (Microsoft 365 / IMAP) via n8n, queue, no double processing (Message-ID).
2. **Real ERP interface** behind the existing `ERPConnector`: read for matching, write only after approval.
3. **Login and roles** in the review desk; audit log in a database instead of a file.
4. **Test set** of 100–200 anonymised real e-mails; tune thresholds on it (goal: wrong assignment ≈ 0, rather more reviews).
5. **Metrics:** share of "please approve", how often people change the proposal, time to first reply, emergency response time.
6. **Cost:** rule mode ≈ €0; one AI call ≈ 1,500 tokens per e-mail – fractions of a cent with paid EU models.
7. Analyse attachments (photos), virus scan.
