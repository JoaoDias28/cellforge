# Task 029 — Studio task and recipe authoring

## Goal
Author valid BehaviorTree.CPP tasks and immutable recipe versions in Cell Studio without directly editing source files, ensuring compiler-equivalent validation, strict lifecycle rules, and execution compatibility with the Task 024 supervisor.

## Scope
Included:
- BehaviorTree.CPP task authoring driven by installed plugin node/port manifests and built-in control/decorator nodes.
- Canonical BehaviorTree.CPP v4 XML generation and parsing with round-trip preservation of non-runtime UI layout metadata.
- Typed port mapping, blackboard dependency resolution, decorator configuration (retry, timeout, repeat, etc.), and compiler-equivalent static validation.
- Schema-driven recipe forms, units and numerical ranges, version diffing, and capability compatibility checks against cell components.
- Strict recipe lifecycle enforcement (`DRAFT -> VALIDATED -> TESTED -> APPROVED -> RETIRED`), immutable released versions, and refusal of unvalidated/untested approvals.
- Integration into Studio application service, undo/redo command stack, and Omniverse Kit UI panels.
- Deterministic test coverage and validation of saved XML against the Task 024 supervisor.

Excluded:
- Arbitrary code generation outside declared BT node plugins.
- Bypassing functional safety rules or implementing safety logic in Python / software.
- Studio-only production approvals without evidence.
- Hardware-specific calibration changes (covered in Task 028).

## Current state
- Tasks 015–017 provide paired `cell.yaml` and USD buffers, transactional Save, stable component IDs, placement/removal, typed connections, and whole-pair undo/redo.
- Task 024 provides the canonical pen BehaviorTree runtime and supervisor node validation (`cellforge_supervisor`), compiling BehaviorTree.CPP XML with blackboard validation and skill invocation.
- Task 028 provides spatial configuration, component configuration/variants, and immutable calibration binding.
- `cellforge_bundle.compiler` provides compiler-stage validation for behavior tree plugins, node manifests, blackboard pointer data flow, and process retry prohibition.
- `recipe.schema.json` defines canonical recipe structure, and `examples/pen_engraving/recipe.yaml` defines the reference recipe.

## Design
### Task Authoring Service (`TaskAuthoringService`)
- Discovers plugin manifests in `behavior_tree_plugins/*.json` and registers standard BTCPP v4 control and decorator nodes.
- Converts between in-memory `TaskTree` / `TaskNode` hierarchy and canonical BehaviorTree.CPP v4 XML (`<root BTCPP_format="4" main_tree_to_execute="..."> ... </root>`).
- Retains UI layout metadata (positions, collapsed states, annotations) in non-runtime XML attributes / tags without modifying execution semantics.
- Performs compiler-equivalent validation:
  - Unknown node types and unknown ports;
  - Missing required ports;
  - Output/inout port blackboard pointer format (`{key}`);
  - Input port blackboard dependency resolution against seeded keys and preceding output ports;
  - Process retry prohibition (e.g. `ExecuteProcess` under `RetryUntilSuccessful`);
  - Capability resolution against placed cell components.

### Recipe Authoring Service (`RecipeAuthoringService`)
- Loads and inspects recipes referenced in `cell.yaml`.
- Provides schema-driven field definitions, data types, units (e.g. `s`, `mm`, `deg`, `scale`), and valid ranges.
- Computes structured diffs across versions (parameters, timeouts, limits, capabilities, status).
- Enforces lifecycle state machine:
  - Transitions: `DRAFT -> VALIDATED -> TESTED -> APPROVED -> RETIRED`.
  - Approved/Retired versions cannot be directly mutated.
  - Edits on an approved/retired recipe create a new draft version (`version = N + 1`, status `DRAFT`), stored in a new file (e.g. `recipes/{id}_v{version}.yaml`), bound in `cell.yaml`, while preserving predecessor files unaltered.
  - Reverting edits on validated/tested drafts resets state to `DRAFT`.
  - Rejects skipping lifecycle states or approving without simulation evidence.

### Studio Application and UI Integration
- Extends `ProjectBackend` and `StudioApplication` with undoable task and recipe commands.
- `ProjectCommandService` validates task XMLs and recipe YAMLs in `contents.artifacts` during `inspect()` and `save()`.
- Kit extension panels expose task graph inspection, port binding, recipe forms, diff viewer, and version creation.

## Work sequence
1. Implement `TaskAuthoringService` with plugin discovery, BTCPP v4 XML parsing/generation, layout metadata preservation, and compiler-equivalent validation.
2. Implement `RecipeAuthoringService` with schema validation, units/ranges, version diffing, lifecycle rules, and immutable version creation.
3. Integrate services into `ProjectCommandService`, `StudioApplication` (with undoable commands), and Kit UI panel views in `extension.py`.
4. Add comprehensive unit and acceptance tests for task authoring, recipe authoring, and application commands.
5. Add verification script `scripts/verify_studio_task_recipe_authoring.py` validating end-to-end authoring, XML compilation, and supervisor compatibility.
6. Run all required checks (`ruff`, `mypy`, `pytest`, `validate-examples`, verification script), commit, push branch, open PR, and verify CI.

## Validation
- `uv run --frozen pytest --basetemp .pytest-tmp -o cache_dir=.pytest-cache/task029 src/kit/cellforge.studio/tests`
- `uv run --frozen python scripts/verify_studio_task_recipe_authoring.py`
- `uv run --frozen python -m cellforge_domain.example_validation --schemas schemas --examples examples/pen_engraving`
- `uv run --frozen ruff format --check .`
- `uv run --frozen ruff check .`
- `uv run --frozen mypy ...`
- Local Git verification: `git status --short`, `git log -1 --oneline`.

## Risks and rollback
- Risk: Non-runtime layout metadata might break BehaviorTree.CPP C++ parser.
  - Mitigation: Use standard BTCPP v4 attributes or models that `BT::createTreeFromText` ignores, and verify with supervisor gtest / tree validation.
- Risk: Recipe versioning could inadvertently overwrite predecessor files.
  - Mitigation: Enforce strict path isolation for new recipe versions and ensure `ProjectContents.artifacts` adds new files rather than overwriting existing version paths.
- Rollback: Revert task branch without affecting previous task milestones.

## Progress
- [x] 2026-08-17 — Synced with default branch, checked out `task/029-studio-task-recipe-authoring`, verified prerequisite commits (024 and 028 in history).
- [x] 2026-08-17 — Executed baseline tests and validated example schemas.
- [x] 2026-08-17 — Implemented `TaskAuthoringService` and `RecipeAuthoringService`.
- [x] 2026-08-17 — Integrated into `StudioApplication`, `ProjectCommandService`, and `extension.py`.
- [x] 2026-08-17 — Implemented unit and acceptance test suites and verification script.
- [x] 2026-08-17 — Ran lint, type check, test suites, and example validation.
- [x] 2026-08-17 — Verified full acceptance probe `scripts/verify_studio_task_recipe_authoring.py`.

## Decisions
- 2026-08-17 — Separate task authoring and recipe authoring into pure domain/application services (`task_service.py` and `recipe_service.py`) keeping Kit UI purely declarative and headless-testable.
- 2026-08-17 — Store layout metadata in XML attributes/tags that round-trip cleanly and are ignored by standard BehaviorTree.CPP v4 parsers.
- 2026-08-17 — Enforce immutable recipe versions by making `APPROVED` and `RETIRED` recipes read-only; editing creates a new version N+1 with status `DRAFT`.

## Results
- `TaskAuthoringService` discovered built-in BTCPP control/decorator nodes and repository plugin nodes, preserved layout metadata on XML round-trips, and enforced compiler-equivalent static validation (unknown nodes/ports, missing required ports, invalid/unresolved blackboard pointers, and process retry prohibition).
- `RecipeAuthoringService` implemented schema-driven field forms with units/ranges, version diffing, strict lifecycle state transitions (`DRAFT -> VALIDATED -> TESTED -> APPROVED -> RETIRED`), required evidence on tested/approved versions, and immutable next-version creation without predecessor mutation.
- Extended `cellforge_bundle.compiler` to tolerate non-runtime layout attributes (`_x`, `_y`, `_collapsed`) and `<TreeNodesModel>`.
- Fully integrated task and recipe authoring into `StudioApplication` (with undo/redo), `ProjectCommandService`, and Omniverse Kit UI panels in `extension.py`.
- All 67 `cellforge.studio` tests passed, all 384 workspace tests passed, `validate-examples` passed, and `verify_studio_task_recipe_authoring.py` verified end-to-end authoring, validation rejections, transactional save, and runtime bundle compilation.

