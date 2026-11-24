# Tests and security

*English version of [../07_Tests_und_Sicherheit.md](../07_Tests_und_Sicherheit.md).*

## How I tested
- **By hand, end to end:** went through all 14 examples in the review desk, processed my own e-mails live (with and without AI),
  sent them through n8n and followed them to the review list and approval – locally and online.
- **Automated:** **993 tests** with `pytest`, run with `uv run pytest` (about 1 minute). Every defect found gets a test so it cannot come back.
- **Example scenarios:** `uv run intake-scenarios` checks all 14 cases against their expected result (status, contract, urgency,
  failed checks). In the review desk the same works with one click: *Rules → Re-check all examples*.

## What the tests cover

| Area | Tests | Examples |
|---|---|---|
| Reading without AI (rule mode) | 457 | floors in words and digits, "2. bzw. 3. OG", "nicht links", house numbers, postcode/town, English |
| Edge cases found while testing | 115 + 75 | unusual wording, someone writing for another person, "Hinterhaus", "Wohnung 5" |
| Matching | 47 | points per signal, contradiction = exclusion, threshold, gap, inactive contract |
| Urgency | 43 | rules set the minimum, AI may only raise it, heating season, safety advice for gas |
| Reply and task | 47 | language of the e-mail, no ERP data when the match is unclear, question to the tenant |
| AI connection | 47 | invalid AI answer, outage, rate limit → automatic rule mode |
| Approval and actions | 39 | nothing without approval, manual assignment only with a reason, no send command in the code |
| API | 38 | seal, version check, step order, access protection |
| Example scenarios | 39 | the 14 cases with exact expected results |
| Other | 46 | earlier cases, translations, n8n export, hosting |

## Security – what is there
- **No automatic sending.** There is no send function in the code; the draft is only copied to the clipboard.
- **No action without approval.** Contract actions go through one approval point; every approval is in the audit log.
- **Access protection online:** password for the review desk, own n8n account, the n8n webhook needs a secret token.
- **The AI must quote:** address, floor and side returned by the AI must appear word for word in the e-mail – otherwise they are not used (a floor missing this way means review).
- **Sealed cases:** the server signs every case (HMAC). A changed proposal is rejected.
- **Version check:** if rules or ERP data change, earlier approvals no longer count – the case must be checked again.
- **Secrets only in `.env`** or in the Render settings, never in the code.
- **Privacy:** made-up test data, plus one own test tenant with my name and e-mail address. In "Groq live" mode the e-mail text goes to a US provider – the UI says so. With a Groq key set, this also applies to the reading translation of own e-mails in the language switch.

## Security – deliberately missing (needed for production)
- User accounts and roles (today one shared demo password).
- A persistent database (today files; a restart of the free hosting instance empties the review list).
- Rate limiting, monitoring and alerts.
- A data processing agreement (GDPR) with an EU AI provider, or a local model.
- Real mailbox and ERP connections with their own restricted access.

More on limits and risks: [03_Assessment.md](03_Assessment.md).
