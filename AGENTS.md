# CellForge repository instructions

## Mission

Build a simulation-first industrial robot-cell engineering platform. Preserve a strict boundary between engineering software, production control, and independent functional safety.

## Required working method

- Read `SYSTEM_SPEC.md`, the relevant file in `docs/`, and the assigned task before changing code.
- For work longer than one focused change, create or update an ExecPlan using `PLANS.md`.
- Implement only the requested task and its direct prerequisites. Do not silently expand scope.
- Keep commits reviewable and preserve backward-compatible schemas unless the task explicitly permits a breaking change.
- Prefer existing ROS 2, MoveIt, Isaac Sim, OpenUSD, and industrial protocol capabilities over custom replacements.
- Never implement safety logic in ROS, Python, Isaac Sim, a web service, or an AI model. Software may display safety state and refuse operation, but safety enforcement belongs to rated hardware.
- Never allow an unapproved recipe, unvalidated component configuration, or unknown material classification to authorize a physical process.
- Never add a production dependency without documenting its license, maintenance status, reason, and removal path.

## Task and Git lifecycle

These rules apply to every implementation task under `codex/tasks/`.

### At the start of a task

1. Identify the exact assigned task file and its task number.
2. Read:
   - this `AGENTS.md`;
   - `SYSTEM_SPEC.md`;
   - `PLANS.md`;
   - the assigned task file;
   - the relevant architecture documents;
   - the implementation and Git history produced by prerequisite tasks.
3. Run:

   ```bash
   git rev-parse --show-toplevel
   git status --short
   git log --oneline -5
   ```

4. Except for initial repository creation in Task 001, do not begin implementation when:
   - the repository has no commits;
   - the working tree contains unexplained changes;
   - the required prerequisite task is not present in Git history;
   - the assigned task file cannot be found.

5. If the environment is a normal local checkout and the current branch is `main`, create a task branch named from the assigned task, for example:

   ```bash
   git switch -c task/002-domain-models
   ```

   If the Codex environment already provides an isolated task branch, remain on that branch.

6. Run the relevant existing checks before editing. Record any pre-existing failures and do not misrepresent them as regressions caused by the current task.

### During a task

- Keep changes limited to the assigned task and its direct prerequisites.
- Do not modify or amend existing commits.
- Do not commit secrets, credentials, generated caches, local environment files, build trees, or machine-specific configuration.
- Add tests with the implementation.
- Update the active ExecPlan as discoveries and decisions are made.
- Do not start the next numbered task.

### Before committing

1. Run all acceptance checks specified by the task.
2. Run the repository checks applicable to the changed area.
3. Inspect the complete change:

   ```bash
   git status --short
   git diff
   git diff --check
   ```

4. Resolve unintended changes, formatting errors, temporary files, and misleading placeholders.
5. Stage only the completed task:

   ```bash
   git add -A
   git diff --cached --check
   git diff --cached --stat
   ```

### Required task commit

Every completed implementation task must end with a Git commit.

Use this commit-message format:

```text
task(NNN): concise task description
```

Example:

```bash
git commit -m "task(002): add domain models and schema loader"
```

Rules:

- Task 001 may create the repository's initial commit.
- Do not amend or rewrite earlier task commits.
- Do not combine multiple numbered tasks in one commit.
- If Git identity, permissions, signing, hooks, or another environment restriction prevents committing, the task is not fully complete. Report the exact blocker and the exact command the user must run.
- Never claim that a commit exists unless `git log -1 --oneline` displays it.

### Required completion verification

After committing, run:

```bash
git status --short
git log -1 --oneline
```

A completed task should have a clean working tree. If files remain modified or untracked, explain exactly why.

### Required GitHub publication and merge

After the task commit and local completion verification:

1. Push the task branch to `origin` and set its upstream.
2. Open a ready-for-review pull request against the default branch. Do not leave a completed task as a draft.
3. Wait for every required GitHub check to finish. Inspect failing job logs, fix only failures within the assigned task or its direct prerequisites, rerun the applicable local checks, and push additional reviewable commits as needed.
4. Do not bypass branch protection, required reviews, or failing checks. Merge only after every required check passes and GitHub reports the pull request as mergeable.
5. Merge the pull request, update the local default branch with a fast-forward-only pull or merge from `origin`, and verify that the task commit is present in its history.
6. Confirm the final branch, pull-request, CI, merge, and local-repository state with:

   ```bash
   git status --short
   git log -1 --oneline
   ```

A numbered implementation task is not fully complete until its pull request is merged and the updated default branch has been pushed or fetched locally. If authentication, permissions, GitHub availability, required reviews, or another external restriction prevents publication or merge, stop and report the exact blocker instead of claiming completion. Do not start a dependent numbered task until its prerequisite pull request is merged.

The final task report must include:

- assigned task number and filename;
- branch name;
- commit hash and subject;
- implementation summary;
- important files changed;
- commands and tests executed;
- passing, failing, skipped, and unavailable checks;
- assumptions and architecture decisions;
- blockers or prerequisites for the next task;
- pull-request URL and number;
- required GitHub checks and their final results;
- merge commit hash and confirmation that the remote and local default branch include the task;
- confirmation that later tasks were not started.

### Required next-task prompt

At the end of the final report, generate one ready-to-copy prompt for the next eligible task from `CODEX_TASK_INDEX.md`.

The generated prompt must:

- use the exact next task filename;
- require reading `AGENTS.md`, `SYSTEM_SPEC.md`, `PLANS.md`, and the task file;
- require checking Git status and prerequisite history;
- restrict work to that task and direct prerequisites;
- require applicable regression and acceptance tests;
- require a task-scoped commit;
- require the same completion report;
- stop before the following task.

If no next task is eligible, explain which dependency or decision is blocking it instead of inventing a prompt.

## Architecture rules

- `cell.yaml` is the canonical operational graph. The USD stage is the canonical spatial scene. They share immutable component instance IDs and must validate together.
- Components communicate through declared capabilities and ports, not direct package-specific imports across layers.
- Simulation and hardware adapters implement the same contract.
- The behavior tree coordinates work; MoveIt plans motion; device adapters communicate with equipment; the safety system remains independent.
- Hardware-facing nodes must support cancellation, timeout, explicit readiness, deterministic fault codes, and safe restart semantics.
- No ROS node may rely on a browser, engineering workstation, external internet connection, or cloud service for normal production.
- Generated deployment bundles are immutable and content-addressed.

## Languages and quality

- Python: Python 3.12 where compatible; use type hints, Pydantic models, Ruff, mypy, and pytest.
- ROS C++: C++20 where supported by the ROS distribution; use ament_cmake, clang-format, clang-tidy, and gtest.
- ROS Python packages: use ament_python and rclpy; keep hardware timing-sensitive paths out of Python.
- JSON schemas use Draft 2020-12.
- YAML examples must validate against the corresponding JSON schema after YAML-to-JSON parsing.
- Public interfaces require documentation and contract tests.

## Tests required before completion

Run the tests applicable to the changed area. At minimum:

```bash
make lint
make test
make validate-examples
```

For ROS changes also run:

```bash
make ros-build
make ros-test
```

For Isaac Sim extension changes, run the headless extension test command documented by the task. If Isaac Sim is unavailable in the environment, add deterministic unit tests for non-Kit logic and clearly report the unexecuted integration check.

## Definition of done

A task is complete only when:

- acceptance criteria in the task file pass;
- relevant documentation and schemas are updated;
- tests cover success, invalid input, timeout/cancellation where applicable, and at least one failure path;
- no placeholder silently returns success;
- limitations are recorded honestly;
- generated files are reproducible from source;
- the task has a Git commit;
- `git log -1 --oneline` confirms that commit;
- the task branch has been pushed and its ready pull request has passed every required GitHub check;
- the pull request has been merged and the local default branch includes the task commit;
- the working tree is clean or every remaining file is explicitly explained;
- the final response contains the ready-to-copy next-task prompt.
