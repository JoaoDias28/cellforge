# CellForge CLI

The `cellforge` command is a headless engineering interface. It requires neither ROS nor Isaac Sim
and is not part of the independent functional-safety system.

## Commands

```text
cellforge project init <path>
cellforge validate <project>
cellforge inspect <project>
cellforge schema list
cellforge build <project> --target <profile-id> --mode <mode> --source-revision <git-sha> [--output manifest.json]
cellforge example copy pen-engraving <path>
```

Add `--json` anywhere in a command to emit one deterministic object with `command`, `ok`,
`exit_code`, `message`, `result`, and `errors` fields. Each error has a stable `code`, `severity`,
source-addressable `path`, and human `message`. Human failures are written to standard error; JSON
results are written to standard output for direct parsing by CI.

`project init` creates a valid simulation-only scaffold containing a metadata-only passive workspace
marker. It has no process capabilities, production deployment mode, hardware adapter, or safety
authority. Schema validity never authorizes commissioning or physical execution.

`example copy` refuses to overwrite a path and makes the canonical pen project self-contained by
copying the canonical schemas under `schemas/` and updating the recipe schema reference. `validate`
uses project-local canonical schemas only after verifying that every file is byte-identical to the
schemas bundled with the CLI; otherwise validation fails. It performs Task 003 schema, domain, and
cross-file checks. `build` adds exact component/capability/adapter resolution, source-reference and
behavior-tree checks, recipe/mode policy, target dependency selection, and manifest generation.

## Deterministic build

`build` requires an exact target profile, execution mode, and 40-character lowercase Git commit
hash. It returns the canonical manifest in JSON output and optionally creates a file with `--output`.
An existing output is never overwritten. Repeating a build over byte-identical inputs produces the
same manifest and SHA-256 bundle ID; changing any inventoried source changes its content hash and
therefore the bundle ID.

The compiler selects simulation adapters only for simulation and hardware adapters for
commissioning/production. Production rejects non-qualified components, missing hardware adapters,
unapproved recipes, and unknown material classifications. It then fails closed at the production
evidence placeholder because Task 006 does not yet implement evidence verification. A successful
schema or simulation build is not authorization for physical operation and does not implement a
functional-safety function.

## Stable exit codes

| Code | Name | Meaning |
|---:|---|---|
| 0 | `SUCCESS` | Command completed successfully. |
| 1 | `VALIDATION_FAILED` | The project or document content is invalid. |
| 2 | `USAGE_ERROR` | Command-line arguments are invalid. |
| 3 | `INPUT_NOT_FOUND` | The requested project input does not exist. |
| 4 | `DESTINATION_EXISTS` | A scaffold/copy destination already exists. |
| 5 | `RESOURCE_UNAVAILABLE` | Canonical bundled schemas or examples cannot be loaded. |
| 6 | `OPERATION_FAILED` | A sanitized filesystem operation failed. |

Numeric meanings are backward-compatible public CLI contracts. Future statuses must use new values.
