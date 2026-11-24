# AI usage

*English version of [../05_KI_Nutzung.md](../05_KI_Nutzung.md).*

The idea of the solution, the business rules and all decisions are mine.

For the **implementation** I used LLM tools: to my instructions they wrote plans, texts, code and tests. I reviewed the results, decided what had to be fixed, and approved every change before it
was published.

Inside the product, **Groq** (`openai/gpt-oss-120b`) reads the e-mails – demo data only.

## My decisions
- The system never guesses: unclear or missing information → **review needed**, no action on a contract.
- The reply to the tenant is **never sent automatically** – drafts only, a person approves.
- **Free tools only**; the app also runs without any API key (rule mode, recorded AI answers).
- The AI only reads; **fixed rules choose the contract** (points per signal, threshold, gap, contradiction, contract active).
- German floor counting (EG = ground floor); missing or unclear floor → always ask the tenant.
- Unknown sender address: do not block, but a clear warning and three options for the case worker.
- Own review desk, **n8n as the visible process**, everything readable in German and English, free hosting.
- Quality rule: every defect found is covered by a test (993 tests, 14 example scenarios).

## What I checked myself
- The whole application step by step: I went through all example test cases myself.
- Processed my own e-mails live and checked them end to end – from the inbox through n8n to the review list and approval.
- Ran the n8n process on my laptop against the online app.
