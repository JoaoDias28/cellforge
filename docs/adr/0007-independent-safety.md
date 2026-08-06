# ADR 0007: Keep functional safety independent

## Status
Accepted and non-negotiable.

## Decision
Functional safety is implemented by rated hardware and manufacturer safety functions. CellForge consumes status and models requirements but does not enforce protective functions.

## Consequences
No software feature may introduce an interlock bypass or imply safety certification.
