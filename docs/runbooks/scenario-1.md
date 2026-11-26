# Scenario 1 — Meeting/Email to Execution (plan §11.1)

Runbook for the presenter driving the deterministic replay demo
(`make demo`; AI in replay mode — `AI_ENABLED=false`, `LLM_MODE=replay`).

Prereq: seeded demo state (`make seed-demo`), API on `http://127.0.0.1:8000`.

## Presenter actions

| Step | Action |
|---|---|
| 1 | Open the **AI Inbox** (`/ai/inbox`) and confirm the extracted item "Replace pump assembly on line 3" is pending |
| 2 | Expand the duplicate panel on the item: existing task "Order replacement seal kit" is flagged `duplicate`; a related project "Compressor K-201 Overhaul" is proposed |
| 3 | Reviewer edits the owner hint and **accepts** one item, **merges** the duplicate, **rejects** another with a reason |

## System behaviour

| # | Behaviour |
|---|---|
| 1 | The m365-sim transcript + Outlook email thread arrive via webhook sync; artifacts land with `ai_processing_allowed = true` |
| 2 | PII redaction → chunk → extraction → evidence-verification guard; ≥ 1 verified `extracted_item` per seeded action; **0 unverified quotes surface** |
| 3 | Owner resolution: fuzzy match on attendees (synthetic participants prioritised); due date resolved from the phrase "by Friday" |
| 4 | Duplicate detection: retrieval over same-owner/project + `adjudicate_duplicate` LLM replay; link proposal to project/objective |
| 5 | Promotion: accept → `task`/`commitment` with `derived_from` link + back-reference + hash-chained audit |
| 6 | Provenance: quote, speaker, timestamp, model, prompt version — deep link opens the source artifact |
| 7 | Move task to done → commitment status updates (registration run through the approvals workflow) |
| 8 | Injection beat: the email with the injected instruction yields no suggestion |

## Assertions (API-level; covered by `tests/test_ai_scenario1.py` + `tests/test_ai_pipeline.py`)

- `source_artifact` rows exist for approved sources with `ai_processing_allowed = true`
- `extracted_item` suggestions are verified (0 hallucinated quotes)
- `ai_suggestion` rows carry `model`, prompt `@v1+hash` stamps, reviewer, timestamps (provenance)
- Promotion creates `work_item(type=task)` with `derived_from` links + audit entries
- Feedback signals are recorded for rejected/edited suggestions (T4.12)
