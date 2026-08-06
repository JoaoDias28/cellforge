# CellForge CLI

The `cellforge` command is a headless engineering interface. It requires neither ROS nor Isaac Sim
and is not part of the independent functional-safety system.

## Commands

```text
cellforge project init <path>
cellforge validate <project>
cellforge inspect <project>
cellforge schema list
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
cross-file checks; spatial USD, capability resolution,
behavior-tree semantics, approvals, and deployment policy belong to later tasks.

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
