# Actual effort

*English version of [../06_Aufwand.md](../06_Aufwand.md).*

| | Time |
|---|---|
| **Core of the task** (the 9 steps, working) | approx. **36 minutes** |
| Extras (tests for edge cases, UI, n8n, German/English, hosting, documents) | approx. 11.5 hours |
| **Total** active work, spread over several days | approx. **12 hours** |

Based on my time log: [docs/TIMELOG.md](../../docs/TIMELOG.md). Breaks are not counted.
I did the implementation with an LLM.

## The core (18 Nov 2026)

| Activity | Time | Duration |
|---|---|---|
| Read the task, look at the company, write down my understanding | 19:08–19:12 | 4 min |
| Plan: priorities, technology, handling uncertainty | 19:12–19:21 | 9 min |
| Data model, rules, example ERP, matching, 14 test cases | 20:07–20:15 | 8 min |
| Reading without AI, earlier cases, urgency, reply, task, approval | 20:15–20:30 | 15 min |
| **Core total** | | **approx. 36 min** |

So the core was well under 90 minutes.

## Why more than 90 minutes in total?

The task does not expect a perfect solution, and I prioritised the core so that it fits into 90 minutes.
I invested the extra time on purpose, because you want to change rules live in the interview. For that I needed:
- tests that show at once whether a rule change breaks something,
- a UI that explains every decision,
- a visible process in n8n,
- an online version, so you can try the prototype without installing anything.
