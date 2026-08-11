# Artifacts and changeset

## Repository run directory

Use `agent-team/runs/<run-id>/` in every repository and commit it with the submission.

| File | Owner | Purpose |
|---|---|---|
| `run-config.json` | initializer | immutable parameters and configuration hash |
| `roster.json` | leader | versioned reusable task identities and routes |
| `spec.md` | leader | scope, interfaces, acceptance criteria |
| `plan.md` | leader/planning role | ordered work, tests, risks |
| `role-reports/<order>-<role>.md` | ordinary worker | human-readable stage evidence |
| `handoffs/<order>-<role>.json` | ordinary worker | compact structured delta for the next stage |
| `decisions.jsonl` | all through owner | append-only decisions |
| `development-log.md` | code-writing roles | commands, changes, tests, deviations |
| `review.md`, `review.json` | review gate | human and machine-readable verdict |
| `alignment-input.json` | leader | compact manager-hub alignment input |
| `alignment.md` | leader | manager decision applied locally |
| `result.json` | leader | approved local outcome |

## Configuration and roster

Use schema version 3. `run-config.json` contains `repositoryCount`, team, repository, `configurationHash`, ordered roles, `reviewGateRole`, and `maxReviewRounds`. Treat it as immutable.

In `roster.json`, keep the same hash plus `rosterVersion`. For each task record title, thread ID, host ID, status, and `lastVerifiedAt`. Mark workers as `ordinary` or `review-gate`. Only ordinary workers have `role-reports` and `handoffs`; the gate worker owns `review.md` and `review.json`.

## Handoff

Use this minimum shape:

```json
{
  "schemaVersion": 3,
  "runId": "<run-id>",
  "role": "developer",
  "order": 2,
  "status": "DONE",
  "summary": "Implemented API validation",
  "changedFiles": ["src/api.py"],
  "tests": [{"command": "pytest", "outcome": "passed"}],
  "decisions": ["D-003"],
  "risks": [],
  "request": null,
  "completedAt": "<UTC ISO-8601>"
}
```

## Review and result

`review.json` records `round`, `maxRounds`, verdict, reviewer, findings, and tests. Require `1 <= round <= maxRounds`. Every finding names a valid `ownerRole` and valid `affectedRoles`. On approval, require `result.json.review` to match the verdict and round and require `executedRoles` to contain every ordinary role.

## Manager-hub alignment

Each `alignment-input.json` contains status `SUBMITTED`, `provides`, `requires`, migrations, desired commit order, rollback, tests, and risks. The manager compares all inputs once. Each leader records the same manager decision identifier or summary in `alignment.md` with `Status: ALIGNED`.

## Changeset

Write `<manager-workspace>/changesets/<run-id>.json`, creating `changesets/` when absent and refusing overwrite without explicit authorization.

Schema version 3 includes the repository count and, for every repository, commit metadata, changed files, configuration hash, worker roles, ordinary stage roles, review gate, maximum and actual review rounds, and records directory.

The builder enforces:

- exact clean Git roots and the expected repository count;
- matching schema-3 configuration and roster hashes;
- all fixed records, dynamic ordinary-role reports, and handoffs exist in one batched Git tree listing;
- every ordinary handoff is `DONE` and matches its role;
- the gate reviewer issued `APPROVED` within the limit;
- result verdict, round, and executed roles agree;
- alignment input is `SUBMITTED` and local alignment is `ALIGNED`;
- the submission commit contains this run's records.
