# SQL Review Environment

Train AI agents to review, fix, and optimize SQL queries.

## Description
A comprehensive OpenEnv component leveraging an in-memory SQLite database to simulate real-world code review and optimization tasks for SQL.

## Interaction Spaces

### Observation Space
| Property | Type | Description |
|---|---|---|
| task_id | string | The active task |
| db_schema | string | Active schema representation |
| query | string | Current SQL query state |
| error_message | string (nullable) | Last execution error |
| step | integer | Current episode step |

### Action Space
| Property | Type | Description |
|---|---|---|
| sql | string | SQL command to execute |

## Tasks
1. **syntax-fix** (easy): Fix deliberate syntax errors in a query.
2. **performance-tune** (medium): Rewrite a query to optimize scanning and use indexes.
3. **schema-design** (hard): Convert business logic to a suite of `CREATE TABLE` statements.

## Setup
```bash
docker build -t sql-env .
docker run -p 7860:7860 sql-env
```

## Baseline Scores
- task 1: 1.0
- task 2: 0.9
- task 3: 1.0
