# Test Cases

The migration agent was tested against normal records as well as
records containing missing, inconsistent, and invalid data.

## 1. File ingestion

| Test | Input | Expected Result |
|---|---|---|
| Multiple source files | Employee files with different column names | Records are combined into a common structure |
| Empty file | CSV with headers but no records | File is handled without crashing |
| Different column names | `Name`, `Full Name`, `employee_name` | Fields are mapped to the target schema |

## 2. Data cleaning

| Test | Input | Expected Result |
|---|---|---|
| Extra whitespace | `" Vikas Rao "` | Whitespace is removed |
| Different casing | `"VIKAS RAO"` | Value is normalized where safe |
| Date format difference | `2021-01-15`, `15/01/2021` | Converted to the target format |
| Invalid date | `2021/13/40` | Value is rejected/cleared and surfaced when required |
| Duplicate record | Same employee in two files | Duplicate is detected and reconciled |

## 3. Validation and escalation

| Test | Input | Expected Result |
|---|---|---|
| Valid email | `vikas@gmail.com` | Record passes validation |
| Invalid email | `not-an-email` | Record is flagged |
| Missing required field | Missing employee ID | Record is not pushed |
| Ambiguous mapping | Source field could map to two targets | Human review is requested |

## 4. Human review

| Test | Action | Expected Result |
|---|---|---|
| Approve | Approve an escalated record | Record continues to migration |
| Correct | Modify an invalid value | Corrected value is used |
| Reject | Reject a record | Record is not pushed |
| Audit | Review the action | Change and reason are visible |

## 5. Target integration

| Test | Scenario | Expected Result |
|---|---|---|
| Successful push | Target API returns 201 | Record is marked successful |
| Temporary failure | Target API returns 503 | Retry is attempted |
| Repeated failure | Target continues failing | Record is marked failed/escalated |
| Rollback | Previously pushed record is reverted | Target record is removed/reverted |
| Audit trail | Push/retry/rollback occurs | Actions are recorded |

## 6. Edge cases

The agent was also tested against records containing missing fields,
invalid dates, invalid emails, duplicate records and partially populated
employee data.