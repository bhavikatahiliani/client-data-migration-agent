# AI Client Data Migration & Integration Agent

A small, customer-facing Flask prototype for migrating messy HR/CRM exports into a canonical employee schema. It combines deterministic data engineering with an open-source LLM (optional Ollama/Qwen) for semantic field mapping, explicit confidence thresholds, human escalation, mock target API integration, retry/rollback, and an audit trail.

## What it demonstrates

- Multi-file CSV/XLSX ingestion and reconciliation
- AI-assisted source → target mapping
- Safe normalization: whitespace, casing, dates, emails, phones
- Duplicate detection with deterministic keys + fuzzy similarity
- Validation with bounded repair attempts
- Human-in-the-loop escalation queue
- Per-record mock target API push
- Retry of failed records only
- Rollback of a migration
- Immutable-style audit events stored in SQLite
- Optional Ollama/Qwen integration; deterministic fallback keeps the demo runnable without a local model

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

### Optional open-source AI model

Install Ollama and pull a model such as Qwen:

```bash
ollama pull qwen2.5:3b
```

Then:

```bash
export OLLAMA_MODEL=qwen2.5:3b
export OLLAMA_URL=http://localhost:11434/api/generate
python app.py
```

If Ollama is unavailable, the agent uses the same confidence/escalation framework with a deterministic semantic mapper. This is intentional: the migration workflow must not fail merely because an optional model endpoint is unavailable.

## Demo

1. Click **Load Demo Dataset**.
2. Review the autonomous mapping/cleaning summary.
3. Open **Needs Review**. The demo contains intentionally ambiguous `Start Date` data and a conflicting duplicate.
4. Approve/correct/reject the escalations.
5. Push to Target.
6. Inspect per-record success/failure, retry failed records, and the audit log.
7. Roll back the migration if desired.

## Autonomy policy

The agent acts without human approval when a transformation is deterministic, low-risk, and above the confidence threshold. It escalates when semantic ambiguity can change business meaning, records conflict on important fields, a mandatory field remains invalid after bounded repair attempts, or the model output cannot be safely parsed.

Suggested thresholds:

- >= 0.90: autonomous mapping
- 0.70–0.89: autonomous only if the mapping is corroborated by sample values and target-field constraints
- < 0.70: human escalation

The UI always shows confidence, evidence, proposed action, and affected sample values so a consultant can resolve an escalation in one glance.

## Architecture

```text
CSV/XLSX files
      |
      v
Ingestion -> schema profiling -> semantic mapping
      |                         |
      |                         +--> Ollama/Qwen (optional)
      v
Normalization -> deduplication -> validation
      |
      +---- high confidence --------------------+
      |                                         |
      +---- ambiguity/conflict -> human review  |
                                                v
                                      canonical employee dataset
                                                |
                                         mock target API
                                                |
                                  success / retry / rollback
                                                |
                                           audit log
```

The LLM reasons about meaning. Python performs deterministic transformations, validation, persistence, API calls, retries, and rollback. This separation reduces the blast radius of hallucinations.

## Project structure

```text
app.py
agent/
  orchestrator.py
  mapper.py
  cleaner.py
  deduplicator.py
  validator.py
  audit.py
api/
  mock_target.py
data/
  employees_a.csv
  employees_b.xlsx
  contacts.csv
  demo_schema.json
templates/
  index.html
  review.html
  audit.html
static/
  app.js
  style.css
tests/
  test_agent.py
```

## One-page write-up points

**Approach:** profile all files, infer mappings using an LLM plus deterministic evidence, normalize safely, reconcile duplicates, validate against a typed target schema, escalate only material ambiguity, then push records independently to a mock API.

**Escalation boundary:** do not ask a human for reversible/low-risk transformations. Do ask when a choice changes semantic meaning or could silently corrupt a business record. Mandatory-field failures are retried with bounded repairs before escalation.

**Next:** persistent job orchestration, richer connector support, model evaluation set, learned mapping memory from consultant corrections, RBAC, encrypted secrets, production-grade idempotency keys, and connector-specific rollback semantics.
