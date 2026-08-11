# Team protocol

## Topology and concurrency

For `N` repositories and `R` roles, create one manager, `N` leaders, and up to `N * R` workers. Run repository pipelines concurrently. Serialize role stages inside each shared repository.

```text
manager
|- leader_<repo-1> -> worker_<repo-1>_<role-1> ... worker_<repo-1>_<role-R>
|- leader_<repo-2> -> worker_<repo-2>_<role-1> ... worker_<repo-2>_<role-R>
`- leader_<repo-N> -> worker_<repo-N>_<role-1> ... worker_<repo-N>_<role-R>
```

Use manager-hub alignment by default. Permit direct peer communication for a named conflict, but copy its conclusion into the decision log and upward report.

## Role contracts

### Manager

- Validate parameters and define the combined goal.
- Create or reuse leaders concurrently.
- Aggregate structured leader alignment inputs.
- Handle exhausted review rounds and unresolved cross-repository conflicts.
- Verify commits and produce the final changeset.

### Leader

- Write the repository specification and plan.
- Create or reuse configured workers concurrently, then schedule their stages serially.
- Send roster references and delta handoffs instead of full history.
- Submit `alignment-input.json`, apply the manager decision, and create the local commit.

### Ordinary worker

- Work only within its responsibility when scheduled.
- Read stable artifacts by path and the immediately relevant handoff.
- Maintain its role report and structured handoff.
- Report evidence, risks, and requests to the leader.

### Review-gate worker

- Run only at the review gate, never as an ordinary role stage.
- Independently inspect the specification, plan, diff, tests, handoffs, and reports.
- Set `APPROVED` or `CHANGES_REQUESTED` and assign every finding to owner and affected roles.
- Never silently fix its own findings.

## State machine

| State | Owner | Required output | Exit gate |
|---|---|---|---|
| `DISCOVERY` | manager | read-only environment facts | no mutation performed |
| `INTERVIEWING` | manager/user | one answered decision card at a time | all dependent decisions resolved |
| `CONFIRMING` | manager/user | compact summary and final card | explicit `Confirm and start` |
| `PARAMETERIZED` | manager | validated configuration | configuration hashes agree |
| `BOOTSTRAPPED` | manager/leader | versioned rosters | tasks confirm roles and routes |
| `SPECIFIED` | leader | spec and plan | measurable acceptance criteria |
| `ROLE_<n>` | ordinary role | role report and handoff | handoff status `DONE` |
| `REVIEWING` | review gate | review records | explicit verdict within limit |
| `REVISING` | affected roles | targeted fixes and refreshed handoffs | review gate can re-review |
| `ESCALATED` | leader/manager | unresolved findings | manager supplies direction or stops run |
| `APPROVED` | review gate/leader | approved result | exact round recorded |
| `ALIGNMENT_SUBMITTED` | leaders | alignment inputs | manager receives every input |
| `ALIGNED` | manager/leaders | one decision reflected in all records | no open conflict |
| `COMMITTED` | leaders | one commit per repository | code and records included |
| `COMPLETE` | manager | changeset JSON | all commits verified |

## Incremental message contract

```text
Run: <run-id>
Repository: <name>
Role: <role>
Roster: <path>#v<version>
Configuration: <hash>
Stage: <state>
Handoff: <path or none>
Changed: <paths only>
Tests: <outcome summary>
Decisions: <IDs only>
Risks: <new or changed risks>
Request: <action requested from parent>
```

Read full artifacts only when the role needs them. Do not paste the whole roster, every earlier report, or unchanged decisions into each message.

## Review findings and targeted reruns

Use this structure:

```json
{
  "id": "F-003",
  "severity": "blocking",
  "ownerRole": "developer",
  "affectedRoles": ["developer"],
  "summary": "Missing validation test",
  "evidence": ["tests/test_api.py:42"]
}
```

Validate roles against `run-config.json`. Sort affected ordinary roles by configured order, run each once, and then re-run the review gate. When `round == maxReviewRounds` and the verdict is not approved, enter `ESCALATED`.

## Session reuse

Reuse a task only when its repository, role, and `configurationHash` match and the task still exists. Record `threadId`, `hostId`, `status`, and `lastVerifiedAt` in the roster. On any roster change, increment `rosterVersion` and notify members with only the new version and path.

## Failure and recovery

- Do not leave `DISCOVERY`, `INTERVIEWING`, or `CONFIRMING` through inference or silence.
- If question cards are unavailable, pause and require Plan mode instead of emitting a bulk form.
- On an edited answer, invalidate and revisit only dependent downstream decisions.
- Reject parameter or configuration-hash drift during resume.
- Stop writers on conflicting edits and preserve user changes.
- Keep failed tests before approval.
- Escalate after the review limit instead of continuing indefinitely.
- Keep leader conflicts before `ALIGNED`.
- Stop changeset generation on dirty worktrees or missing records.
