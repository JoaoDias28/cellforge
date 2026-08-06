# ADR 0002: Use USD for space and YAML for operational semantics

## Status
Accepted.

## Decision
The USD stage is canonical for scene composition and transforms. `cell.yaml` is canonical for component instances, capabilities, connections, runtime configuration, and deployment semantics.

## Rationale
USD is strong for composed spatial data, while Git-friendly YAML and JSON schemas are clearer for operational review, validation, and code generation.

## Consequences
The compiler must validate cross-references and update both representations transactionally. Instance IDs are immutable and shared.
