# Time log

Real times (Europe/Berlin), breaks not counted. **Core** = the 90-minute task itself, **Extra** = what I added on top.
The implementation was done with an LLM; ideas, decisions, testing and approval were mine.

| Date | Time | What I did | |
|---|---|---|---|
| 18 Nov | 19:08–19:21 | Read the task, wrote down my understanding and the plan: matching first, never guess, human approval | Core |
| 18 Nov | 19:21–20:07 | Decided the open points: own review desk, strict floor rule, warning instead of blocking an unknown sender | Extra |
| 18 Nov | 20:07–20:30 | Core built: data model, rules file, test ERP, matching, reader, earlier cases, urgency, reply, task, approval, 14 test cases | Core |
| 18 Nov | 20:30–22:00 | Added the Groq connection, API, review desk and the n8n workflow; tested the examples and asked for fixes | Extra |
| 19 Nov | 00:17–01:53 | Edge cases (unclear addresses and floors); asked for the German/English switch; prepared hosting on Render | Extra |
| 19 Nov | 02:25–02:33 | Published the repository and deployed both services on Render | Extra |
| 19 Nov | 05:01–05:11 | Checked the hosting: login required, no open n8n setup page | Extra |
| 19 Nov | 05:24–06:24 | Safeguards: rules/ERP version per case, signed cases, fixed step order | Extra |
| 19 Nov | 07:01–07:18 | Tested the reader with unusual e-mails, three gaps fixed | Extra |
| 19 Nov | 07:46–08:03 | Planned checks for postcode/town, building parts and flat numbers | Extra |
| 19 Nov | 10:22–12:30 (with a break) | Built those checks, deployed, updated the documents | Extra |
| 23 Nov | 19:30–20:05 | Fixed n8n memory limits on the free hosting plan | Extra |
| 23 Nov | 21:50–01:20 | Tested the language switch and asked for full English/German; n8n texts English first; n8n on my laptop as a backup; own test tenant; start-up fix on Render | Extra |
| 24 Nov | 08:50–09:35 | Illustrated walk-through with screenshots | Extra |

**Total:** core approx. **36 minutes**, all active work approx. **12 hours**.
