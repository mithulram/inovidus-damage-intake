# Groq API – verified reference for `GroqProvider`

Verified by Claude on **2026-11-18** against the live API and current docs. Codex builds `GroqProvider` offline against this file and the recorded fixtures in `examples/llm_recorded/`.

## Endpoint and auth
- `POST https://api.groq.com/openai/v1/chat/completions` (OpenAI-compatible). Header `Authorization: Bearer $GROQ_API_KEY`.
- Client: plain `httpx` (already a dependency) – no extra SDK needed.
- `GET https://api.groq.com/openai/v1/models` listed (2026-11-18): `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `openai/gpt-oss-safeguard-20b`, `qwen/qwen3.8-27b`, llama prompt-guard models.

## Model
- Default: **`openai/gpt-oss-120b`** (override via env `GROQ_MODEL`). Supports **strict** structured outputs.
- Strict-capable per docs: `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `meta-models/muse-spark-open`.
- Free/developer base limits per docs (org-level): 30 RPM, 1K RPD, 8K TPM, 200K TPD for gpt-oss models. One email ≈ 1.3–1.9K tokens (incl. ~0.9K reasoning tokens) → ~100 emails/day on the free tier; enough for the demo, not for production.
- Measured latency: 1.5–2.8 s per email.

## Structured output (strict)
Docs: https://console.groq.com/docs/structured-outputs
```json
"response_format": {"type": "json_schema", "json_schema": {"name": "understanding", "strict": true, "schema": { ... }}}
```
Strict-mode rules: every property listed in `required`; optional = union with `null` (`{"type": ["string","null"]}`); every object `additionalProperties: false`; supported: string, number, integer, boolean, object, array, enum, anyOf, `$defs`/`$ref`. Not supported together with streaming or tool use. Best-effort mode may return HTTP 400 "Generated JSON does not match the expected schema" → our provider retries once, then falls back to offline.

The exact schema and system prompt used for the recordings: `examples/llm_recorded/schema.json`, `examples/llm_recorded/system_prompt.txt`. Settings: `temperature: 0`. User message format:
```
Betreff: <subject>
Absender: <sender_email or "(unbekannt)">

<body>
```

## Response
`choices[0].message.content` is a JSON string matching the schema. `usage` contains `prompt_tokens`, `completion_tokens`, `total_tokens`, `completion_tokens_details.reasoning_tokens`. Response `model` echoes the model id.

## Recorded fixtures (real calls, 2026-11-18)
`examples/llm_recorded/<scenario>.groq.json` = `{ "request": {model, response_format, messages}, "response": {id, model, usage, choices} }` – no headers, no key. Scenarios: S01_original, S04b_partner, S05b_gas, S06_rent_question, S07_english. Observed: addresses/floors copied verbatim ("Musterstr.", "zweite Etage", "2nd floor"); S7 `tenant_name` = null (only signature) → matching falls back to `sender_name`; S6 classified `ANFRAGE_MIETE`; S5b urgency hint `NOTFALL`.

## Data protection
Groq is a US provider; free tier = no DPA for production. Prototype uses synthetic data only. Production: EU-hosted model or DPA (AVV); send only the email text, never ERP data.
