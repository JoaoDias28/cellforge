# ExecPlans

Use an ExecPlan for tasks that span multiple files, introduce a service, change a schema, or require investigation before implementation.

An ExecPlan is a living document stored in `codex/execplans/`. It must remain understandable without chat history.

## Required structure

```markdown
# <plan title>

## Goal
The observable outcome and why it matters.

## Scope
Included and explicitly excluded work.

## Current state
Relevant packages, interfaces, constraints, and evidence from the repository.

## Design
Data flow, APIs, schemas, failure behavior, migrations, and alternatives considered.

## Work sequence
Small ordered changes, each leaving the repository testable.

## Validation
Exact commands and expected evidence.

## Risks and rollback
Likely failure modes, compatibility concerns, and how to revert.

## Progress
- [ ] timestamp — milestone

## Decisions
- timestamp — decision and rationale

## Results
What changed, test results, limitations, and follow-up tasks.
```

## Plan rules

- Do not write “implement everything” milestones.
- Each milestone must have an objective acceptance check.
- Update the plan when discoveries change the design.
- Record schema migrations and interface compatibility explicitly.
- Keep safety assumptions visible.
- Do not mark a hardware integration complete based only on mocks.
