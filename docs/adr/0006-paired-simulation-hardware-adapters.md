# ADR 0006: Pair simulation and hardware adapters behind one contract

## Status
Accepted.

## Decision
Every executable component uses a canonical capability contract with separate simulation and hardware implementations.

## Rationale
This enables sim-first development and avoids separate task programs.

## Consequences
Generic contract tests are mandatory. Fidelity limitations must be declared.
