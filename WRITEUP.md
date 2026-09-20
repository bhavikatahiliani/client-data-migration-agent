# Client Data Migration Agent — Approach

## Problem
Clients export the same employee entity from legacy systems with inconsistent column names, date formats, duplicates, missing values, and conflicting records. The prototype converts those exports into a canonical employee schema and pushes them to a mock target API while keeping a consultant in control of genuinely ambiguous cases.

## Architecture
The system uses Flask as the web/API layer, Pandas/OpenPyXL for ingestion, Pydantic for target validation, SQLite for migration state/audit events, and an optional Ollama-hosted Qwen model for semantic field mapping. Deterministic Python functions perform normalization, deduplication, validation, API calls, retry, and rollback. This separation limits the effect of LLM errors.

## Autonomy boundary
The agent acts autonomously for transformations that are low-risk, reversible, or strongly supported by evidence: whitespace/casing normalization, standard date conversion, email normalization, phone normalization, exact duplicate merging, and high-confidence field mappings. It escalates when semantic meaning is ambiguous, two records may be the same person but have conflicting important values, a required field remains invalid after bounded repair, or model output cannot be safely parsed.

The prototype uses confidence as one signal rather than the only decision criterion. A high confidence score does not override a deterministic safety rule. Human review displays the proposed action, confidence/reason, sample evidence, and a one-click resolution.

## Integration behavior
Each canonical employee is pushed independently to the mock target API. Success and failure are recorded per record. Failed records can be retried without reprocessing successful records. A rollback action removes successfully pushed records from the mock target and marks the migration as rolled back. All major decisions, transformations, human corrections, and target operations are written to the audit log.

## Edge cases covered
Mixed CSV/XLSX files; alias columns; ambiguous `Start Date`; inconsistent date formats; blank/optional values; invalid emails; phone formatting; exact duplicate rows; duplicate IDs with conflicting fields; fuzzy duplicate candidates; low-confidence mappings; malformed/unavailable LLM responses; target API failures; per-record retry; and rollback.

## What I would build next
Production connectors and OAuth/secret management; asynchronous job execution; connector-specific transactional/compensating rollback; stronger entity resolution; model evaluation and regression datasets; persistent memory of consultant-approved mappings; RBAC; PII encryption; rate limiting; and observability/alerting.
