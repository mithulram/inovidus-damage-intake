# Reuse for an internal AI assistant (documents and knowledge)

*English version of [../04_Wiederverwendung_Wissensassistent.md](../04_Wiederverwendung_Wissensassistent.md).*

An internal assistant should answer questions about company documents (e.g. "Which notice period applies to commercial tenants in building X?"). Many building blocks of this solution fit directly:

| Building block from the prototype | Reuse in the knowledge assistant |
|---|---|
| **Intake and normalisation** (read e-mail, clean text) | ingest documents (PDF, DMS, e-mail, wiki), clean and split into sections |
| **Provider interface** (`LLMProvider`: Groq, rules, recording) | same interface for answers; model swappable (EU model, local) |
| **Strict JSON schema + validation** (Pydantic) | answers always with sources in a fixed format; catch invalid answers |
| **ERP connector and case history** | an additional knowledge source next to documents (contract data, open cases) – search/RAG |
| **Points, threshold, gap, "review needed"** | "Answer only with a source. If the source is weak or contradictory: say 'I am not sure' and route to an expert." |
| **Rules file** (`rules.yaml`) | settings without programming: thresholds, allowed sources, blocked topics |
| **Review desk + approval + audit log** | feedback "helpful / wrong", approval of sensitive answers, traceability |
| **Scenarios with expected outcome** | test set of questions and correct answers; checked automatically on every change |
| **Translation layer** | bilingual answers and UI for mixed-language teams |
| **n8n as the visible process** | document import, regular updates, notifications |

**What is new:** a vector search (e.g. pgvector), permissions per document (not everyone may see everything), and citations in every answer.

**Most important carry-over:** the attitude *"uncertainty is a result, not an error"*. Like the matching here, the assistant must never guess; it shows what it relies on and says clearly when it is not sure.
