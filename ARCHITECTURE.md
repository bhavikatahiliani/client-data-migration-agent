# Architecture

## Overview

The application is a small web-based migration agent that takes raw
employee data, maps it to a common target structure, cleans and validates
the records, and pushes the final records to a mock target API.

The main design goal was to keep the agent autonomous for predictable
data issues while stopping for human input when a decision is ambiguous.

## Flow

Source CSV / Excel files
        |
        v
File ingestion
        |
        v
Field mapping
        |
        v
Data cleaning and normalization
        |
        v
Validation
        |
        +---- Valid / confident ----> Push to target
        |
        +---- Ambiguous / invalid --> Human review
                                      |
                                      v
                              Approve / Correct / Reject
                                      |
                                      v
                                Push to target
                                      |
                                      v
                                 Audit trail

## Main Components

### 1. Ingestion

The agent reads multiple source files containing employee information.
Source files may use different column names and formats.

### 2. Mapping and normalization

Source fields are mapped to a common employee schema.

The agent handles safe transformations such as:

- whitespace cleanup
- casing normalization
- date normalization
- duplicate detection
- basic field validation

### 3. Validation and escalation

The agent does not ask for human input for every record.

Records are escalated when the available information is not sufficient
to make a confident decision, such as an ambiguous mapping or a value
that cannot be safely cleaned.

### 4. Human review

The web UI provides the context needed to review an escalated record.
The reviewer can approve, correct or reject the record.

Any correction made by the reviewer becomes part of the migration
history.

### 5. Target integration

After validation, the canonical employee record is sent to the mock
target API using an HTTP request.

The target API returns a success or failure response for each record.

Failed requests can be retried, and rollback is supported for records
that were already pushed.

### 6. Audit trail

The application records important migration actions such as mapping,
review decisions, corrections, pushes, retries and rollback actions.

The goal is to make it possible to understand what happened to a record
without having to inspect application logs.

## Why this boundary?

The agent is allowed to make decisions where the transformation is
deterministic and low risk.

Human review is used when the system cannot confidently determine the
correct value. This avoids both extremes: requiring a human to approve
every field and allowing the agent to silently make uncertain changes.

## Future Improvements

If this were moved beyond the prototype, I would add:

- persistent target storage
- better confidence scoring for mappings
- configurable validation rules
- authentication and role-based access
- background job processing for larger migrations
- richer migration metrics and monitoring