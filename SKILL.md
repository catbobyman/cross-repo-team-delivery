---
name: cross-repo-team-delivery
description: "Orchestrate an optimized, parameterized manager-leader-worker workflow across one or more local repositories: interview the user through one-at-a-time onboarding questions, using native question cards when available and a text fallback otherwise, and require a final confirmation before acting; collect repository count, names, paths, ordered worker roles, responsibilities, and a review gate; reuse compatible Codex tasks; run repositories concurrently while serializing writers inside each repository; exchange compact handoffs; bound review revisions; align leaders through manager aggregation; persist auditable records; coordinate one submission commit per repository; and build a verified manager changeset JSON. Use when the user asks to create repository agent teams, run a role-based reviewed delivery, coordinate multiple repositories or leaders, record development decisions, or bundle repository Git commits into a changeset."
---

# Cross-Repo Team Delivery

Coordinate a user-defined number of repository teams through an efficient, documented, review-gated delivery. Keep the manager as the cross-team authority and preserve leader-worker reporting.

## Load the protocol

Read [references/onboarding-cards.md](references/onboarding-cards.md) before asking initialization questions. Read [references/protocol.md](references/protocol.md) before creating or resuming tasks. Read [references/artifacts-and-changeset.md](references/artifacts-and-changeset.md) before initializing records or generating a changeset.

## Run interactive onboarding first

Treat onboarding as a decision interview, not a form. Ask exactly one decision at a time. When `request_user_input` is available, display one question card, let the tool wait for the answer, update and validate the provisional configuration, and immediately call `request_user_input` again for the next decision in the same active agent turn. Do not end the turn merely to announce that another card is coming, and never require the user to type `next`, `continue`, or `下一张`. Never ask multiple decisions in one card even when the tool accepts multiple questions. Never output a one-shot YAML form.

Before the first card, use read-only inspection to discover facts such as the current workspace, saved projects, exact Git roots, and resumable runs. Ask the user to decide; do not ask for facts that can be discovered. Prefill known values as the recommended option, but still ask the user to confirm them.

Walk through these dependent decisions one-by-one:

1. run mode;
2. delivery goal;
3. repository count;
4. repository identity and exact path, one repository per card;
5. shared role preset or custom roles;
6. custom role count, then each role name and responsibility one card at a time when needed;
7. review-gate role;
8. maximum review rounds;
9. compatible-task reuse policy;
10. final configuration confirmation.

Validate each answer before advancing. On invalid input, explain the issue briefly and show a correction card for the same decision. If the user chooses to edit at the final confirmation, ask which section, revisit only that branch, recompute dependent values, and show the final confirmation again.

Show a compact human-readable summary immediately before the final card. Offer `Confirm and start (Recommended)`, `Edit configuration`, and `Cancel`. Do not inspect repository contents beyond read-only discovery, create tasks, initialize records, edit files, commit, or otherwise start the workflow until the user selects confirmation.

If `request_user_input` is unavailable, continue in the current mode with the text fallback defined in the onboarding protocol. Ask one concise question per assistant response, include the recommended answer and 2-3 clear choices when appropriate, and treat the user's answer as permission to advance directly to the next decision. Do not require a mode switch and do not ask for a separate `next` message. Text fallback changes only the presentation; all validation and the final confirmation gate remain mandatory.

## Establish the run

Begin this section only after the final onboarding card is confirmed.

1. Use the confirmed mode: bootstrap-only, full delivery, or resume.
2. Record the manager workspace, validated parameters, goal, and optional run ID. Generate a safe ID such as `20260811T184500Z-feature-slug` when absent.
3. Inspect instructions and worktree state in every repository. Preserve unrelated user changes.
4. Verify every path with `git rev-parse --show-toplevel`. If any path is not an exact Git root, stop and ask whether to initialize Git or use a different root. Never run `git init` implicitly.
5. Initialize each repository:

   ```powershell
   python <skill-dir>/scripts/init_run.py `
     --repo <repo> `
     --run-id <run-id> `
     --team-name <team-name> `
     --repository-count <repository-count> `
     --worker-role <role-1> `
     --worker-role <role-2> `
     --role-responsibility '<role-1>=<responsibility-1>' `
     --role-responsibility '<role-2>=<responsibility-2>' `
     --review-role <review-role> `
     --max-review-rounds <maximum>
   ```

6. Treat `run-config.json` as immutable. Populate task IDs and statuses in `roster.json`, increment `rosterVersion` on every roster change, and preserve its `configurationHash`.

## Build or reuse the hierarchy

Use Codex thread-management tools, loading them through tool search when necessary.

1. List saved projects and match every exact repository path.
2. Search prior `agent-team/runs/*/roster.json` files for matching repository and `configurationHash`. Verify referenced tasks still exist and have the required roles; reuse valid tasks and copy their IDs into the new roster. Create only missing or stale tasks.
3. Create or resume all repository leaders concurrently. Give each leader the manager ID, repository, run ID, role definitions, review limit, and the paths to `run-config.json` and `roster.json`.
4. Direct each leader to create or resume all configured worker tasks concurrently. Use `<team>_<role>` titles.
5. Send each worker only its role, responsibility, parent ID, `roster.json` path, `rosterVersion`, `configurationHash`, and relevant artifact paths. Do not transmit the full roster or all historical reports in every message.
6. Wait with event-driven task waits, batching only when tool limits require it. Confirm every task's role and route before development.

## Execute the optimized gated workflow

Run different repositories concurrently. Inside one repository, serialize all writers and execute only one stage owner at a time.

1. **Leader specification:** Write `spec.md` and the initial `plan.md`.
2. **Ordinary role stages:** Exclude the review-gate role from this sequence. Run all remaining roles by `order`. Give each role the stable spec and plan paths plus only the immediately relevant handoff and decision IDs. Require it to update its role report and structured handoff.
3. **Implementation records:** Require every code-writing role to append commands, outcomes, tests, deviations, and risks to `development-log.md`.
4. **Single review gate:** Invoke the configured review-gate role only after all ordinary stages complete. Have it inspect the diff, tests, spec, plan, handoffs, and role reports, then write `review.md` and `review.json`. Do not run it earlier as an ordinary stage.
5. **Targeted revision:** On `CHANGES_REQUESTED`, require every finding to name `ownerRole` and `affectedRoles`. Rerun only those roles, in configured order, refresh their handoffs, then invoke the review gate again.
6. **Bounded escalation:** If the current review round reaches `max_review_rounds` without approval, stop automatic work. Have the leader report findings, attempted fixes, tests, and disputed criteria to the manager. Do not fabricate approval or commit.
7. **Approval:** Accept only explicit `APPROVED` from the gate role. Set `result.json.status` to `approved`, record the exact review round and executed ordinary roles, and have workers report completion upward.
8. **Manager-hub alignment:** Each leader writes `alignment-input.json` and sends its path plus a compact summary to the manager. The manager aggregates all inputs and returns one decision. Allow direct leader-to-leader discussion only for named conflicts. Each leader then records `Status: ALIGNED` and the manager decision in `alignment.md`.
9. **Parallel submission:** After every repository is approved and aligned, let leaders create their intentional local submission commits concurrently. Include code and `agent-team/runs/<run-id>/`. Do not push unless requested.
10. **Manager changeset:** Verify all clean worktrees and submission commits, then generate one JSON. Repeat `--repo` once per repository:

   ```powershell
   python <skill-dir>/scripts/build_changeset.py `
     --manager-dir <manager-workspace> `
     --run-id <run-id> `
     --expected-repo-count <repository-count> `
     --repo <team-1>=<repo-1> `
     --repo <team-2>=<repo-2> `
     --manager-thread-id <manager-thread-id> `
     --alignment-summary <manager-summary>
   ```

11. Report every commit ID, changeset path, review rounds, tests, risks, reused and newly created tasks, and unpushed state.

## Enforce authority and efficiency boundaries

- Let the manager assign the combined goal, aggregate alignment, handle exhausted review rounds, and accept the result.
- Let leaders own repository specifications, assignments, local records, and commits.
- Let each ordinary worker own only its configured stage, role report, and handoff.
- Let only the configured review-gate role issue the verdict.
- Permit peer discussion, but record material conclusions and report them upward.
- Share file paths, versions, hashes, decision IDs, and deltas instead of retransmitting full history.
- Do not commit unrelated changes, initialize Git silently, or mark a run complete without every approval, alignment, commit, and changeset entry.

## Resume safely

Read `run-config.json`, `roster.json`, result, handoffs, Git status, and latest decision. Continue from the earliest incomplete gate. Invoke `init_run.py --resume` with identical parameters only to recreate missing templates; reject configuration drift. Verify cached task IDs before reuse, replace stale IDs, increment `rosterVersion`, and notify workers using the new version rather than resending the full roster.
