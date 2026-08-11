# Interactive onboarding

Model onboarding after a decision-tree interview. Ask one question at a time, wait for the answer, and do nothing mutating until the final confirmation.

## Native card rules

- Use `request_user_input` with exactly one entry in `questions` per call.
- Use a header of at most 12 characters, a stable snake-case ID, and 2-3 mutually exclusive options.
- Put the recommended option first and suffix its label with `(Recommended)`.
- Keep option labels short and put paths or detailed consequences in descriptions.
- Rely on the automatically supplied `Other` choice for free-form numbers, paths, names, goals, or responsibility text.
- Let `request_user_input` wait for the answer. After it returns, validate the answer and immediately issue the next card in the same active agent turn.
- Never end a turn only to say that the next card is coming. Never require the user to type `next`, `continue`, or `下一张`.
- Acknowledge an answer only when the acknowledgment adds useful state, such as progress through repeated repository or role entries; then continue immediately.
- Never replace cards with a YAML block, a long questionnaire, or several numbered questions.
- Never create tasks, write records, edit repositories, commit, or push before final confirmation.

## Text fallback

If `request_user_input` is unavailable, do not pause and do not require Plan mode. Continue the same decision sequence in plain text:

- Ask exactly one decision per assistant response.
- State the recommended answer first and give 2-3 concise choices when appropriate.
- Accept a free-form reply for paths, names, counts, goals, or responsibilities.
- Treat the user's answer as the continuation signal; never request a separate `next`, `continue`, or `下一张` message.
- Validate the answer, briefly explain any correction, and ask either the correction question or the next decision.
- Preserve the final summary and explicit confirmation gate before any mutation.

This fallback changes only presentation. It must not become a one-shot YAML block, a long questionnaire, or multiple decisions in one response.

## Discover facts first

Before the first card, use read-only tools to discover:

- current manager workspace;
- saved Codex projects and their exact paths;
- whether each candidate is an exact Git root;
- existing `agent-team/runs/*/run-config.json` and `roster.json` records;
- compatible task IDs that might be reused.

Do not ask the user for a path already discoverable. Present discovered candidates as options and let the user confirm or choose `Other`.

## Decision sequence

### 1. Run mode

Ask whether to run full delivery, bootstrap only, or resume. Recommend full delivery unless the user explicitly asked only to create the team or an existing incomplete run is clearly the target.

### 2. Goal

If the prompt contains a clear goal, present `Use detected goal (Recommended)` with the goal summarized in its description. Offer a refinement choice and allow `Other` for replacement text. If no goal exists, use a card that directs the user to enter it through `Other`.

### 3. Repository count

Recommend the number of explicitly named or confidently detected repositories. Offer the nearest common alternatives, such as 1, 2, and 3, and use `Other` for any other positive integer.

### 4. Repository selection

Repeat one card for each repository slot. Present up to three saved-project candidates by short name; put the absolute path and Git status in each description. Exclude a repository already selected. Allow `Other` for another absolute path.

After each answer, resolve the exact path and verify it exists. If it is not an exact Git root, show a correction card with choices such as `Choose another repo (Recommended)`, `Authorize git init`, or `Cancel setup`. Never initialize Git before explicit authorization.

### 5. Role strategy

Offer:

- `Standard trio (Recommended)`: planner, developer, reviewer;
- `Compact pair`: developer, reviewer;
- `Custom roles`: continue into the custom-role branch.

When the prompt already names roles, recommend `Use detected roles` instead. Always confirm the role set even when it was supplied in the invocation.

### 6. Custom roles

Ask the role count first. Then repeat these cards for each role:

1. role name, using common remaining roles as options and `Other` for a custom name;
2. responsibility, recommending a concise responsibility inferred from the chosen name and allowing `Other` for custom wording.

Use collection order as execution order. After each role, show a brief acknowledgment such as `已记录 2/4：developer — 实现并测试。`, then immediately continue to the next required decision.

### 7. Review gate

Ask which configured role owns `APPROVED` or `CHANGES_REQUESTED`. Recommend a role named reviewer, auditor, QA, or the last quality-focused role. If more than three roles exist, present the best candidates and allow `Other` for another configured role. Reject values outside the configured role set.

### 8. Review limit

Offer 3, 2, and 5 rounds, recommending 3. Use `Other` for another positive integer. Explain that reaching the limit escalates to the manager without committing.

### 9. Task reuse

Offer `Reuse compatible (Recommended)` and `Always create new`. Explain that reuse requires matching repository, role, and configuration hash plus a live task.

### 10. Final confirmation

First display a compact summary containing:

- mode and goal;
- numbered repositories with exact paths;
- ordered roles and responsibilities;
- review gate and maximum rounds;
- reuse policy;
- actions that will occur after confirmation.

Then show one card with:

- `Confirm and start (Recommended)`;
- `Edit configuration`;
- `Cancel`.

On edit, ask which section to change, revisit that branch one card at a time, revalidate dependent choices, and return to this confirmation card. Only `Confirm and start` authorizes task creation and repository writes.

## Resume branch

When the user selects resume, discover incomplete runs and show one run-selection card. After selection, load its immutable configuration, confirm any stale task replacements one at a time, then show the final summary and confirmation. Do not re-ask unchanged configuration decisions unless the user chooses edit; configuration changes require a new run.
