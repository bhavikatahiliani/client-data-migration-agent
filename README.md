# Client Data Migration Agent

A small AI-assisted migration agent built for the Forward Deployed
Engineer take-home assignment.

The application takes raw employee data from source files, maps it to a
common target schema, cleans and validates the data, asks for human
input only when needed, and pushes the final records to a mock target
API.

## What it does

- Ingests employee data from source files
- Handles different source column names
- Maps source fields to a common employee schema
- Cleans and normalizes safe values
- Detects invalid or ambiguous records
- Provides a human review flow
- Pushes validated records to a mock target API
- Supports retry and rollback
- Maintains an audit trail of important actions

## Tech Stack

- Python
- Flask
- SQLAlchemy / database layer
- HTML/CSS/JavaScript
- REST API
- Open-source / AI-assisted components used for migration logic

## Project Structure

```text
agent/       Migration and transformation logic
api/         Mock target API
templates/   Web UI
static/      CSS/static assets
tests/       Automated tests
data/        Sample input data
app.py       Flask application entry point
```

## Setup

### 1. Create a virtual environment

```bash
python3 -m venv .venv
```

### 2. Activate the virtual environment

On macOS / Linux:

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the application

```bash
python3 app.py
```

The Flask application will start locally. Open the local URL shown in
the terminal.

## Demo Flow

A typical migration flow is:

1. Upload the source files.
2. Start the migration.
3. Review the records prepared by the agent.
4. Open an escalated record when the agent needs human input.
5. Approve, correct, or reject the record.
6. Push the approved records to the target.
7. Review the migration result and audit trail.

The demo also shows how a record can be corrected during human review
before the final data is pushed to the target.

## How the Migration Works

The migration flow is intentionally split into a few simple stages:

```text
Source Files
     |
     v
File Ingestion
     |
     v
Field Mapping
     |
     v
Cleaning & Normalization
     |
     v
Validation
     |
     +----------------------+
     |                      |
     v                      v
Confident Record       Needs Review
     |                      |
     v                      v
Push to Target        Human Review
                            |
                     Approve / Correct / Reject
                            |
                            v
                       Push to Target
                            |
                            v
                       Audit Trail
```

The agent handles predictable transformations automatically and uses
human review when it cannot confidently determine the correct action.

## Target Integration

The prototype uses a local mock target API instead of a real external
HR system.

The final canonical employee payload is sent to the mock API over HTTP.
The mock API returns a success or failure response for each record.

For example, a final employee record sent to the target can look like:

```json
{
  "employee_id": "108",
  "full_name": "Vikas Rao",
  "email": "vikas@gmail.com",
  "phone": null,
  "date_of_birth": null,
  "joining_date": null,
  "department": null
}
```

This keeps the prototype self-contained while still exercising the
integration flow that would be used with a real target system.

## Human-in-the-loop

The agent is designed to avoid asking for human confirmation for every
record.

It handles deterministic and low-risk transformations automatically,
such as common formatting and validation cases.

Human review is used when the available information is not enough to
make a confident decision. The reviewer can then approve the record,
correct the value, or reject it.

This keeps the human review step focused on cases where human judgement
actually adds value.

## Retry and Rollback

The target integration handles failures at the record level.

If the target API temporarily fails, the migration can retry the
request. If a previously pushed record needs to be reverted, the
rollback flow can be used.

The migration result records the status of the target operation so that
successful and failed records can be distinguished.

## Audit Trail

The application maintains an audit trail of important migration
actions.

The audit trail is intended to make it clear:

- what happened to a record
- what value was changed
- when a human correction was made
- why a record required review
- whether the target push succeeded or failed
- whether a retry or rollback was performed

This gives an implementation consultant a readable history of the
migration without needing to inspect application logs.

## Testing

The project includes tests covering the main migration flow and
important edge cases, including:

- field mapping
- data validation
- cleaning and normalization
- migration behaviour
- mock target API behaviour
- retry and failure scenarios

Additional manual test cases and edge cases are documented in:

```text
docs/TEST_CASES.md
```

## Sample Data

Sample employee data is available under:

```text
data/
```

The sample data contains normal as well as inconsistent/invalid values
to exercise the cleaning, validation and human-review flow.

## Limitations

This is a prototype intended to demonstrate the migration workflow.

The target system is mocked and is not a production HR system.

For a production deployment, I would add persistent target storage,
authentication and authorization, background processing for larger
migrations, stronger monitoring, and more configurable client-specific
validation rules.

## Documentation

Additional documentation is available in the repository:

- `WRITEUP.md` - approach and reasoning behind the agent's autonomy and
  escalation boundary
- `ARCHITECTURE.md` - high-level architecture and migration flow
- `docs/TEST_CASES.md` - test cases and edge-case coverage

## Running the Tests

If the project is configured with pytest, tests can be run using:

```bash
pytest
```

## Demo

A short demo recording is included with the submission.

The demo covers:

- starting a migration
- reviewing an escalated record
- correcting/approving the record through the UI
- pushing the final data to the mock target
- viewing the migration result
- viewing the audit trail