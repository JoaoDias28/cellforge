# TASK-021 — Bundle install, activation, and rollback

## Goal
Install a compiler-produced immutable bundle on a cell computer only after integrity and target
compatibility checks, activate it atomically through systemd, and automatically restore the prior
known-good release when the new runtime does not become healthy.

## Scope
Included:

- a strict on-disk bundle contract with canonical manifest and checksum verification;
- local target-facts preflight for profile, CPU, OS, ROS, GPU, packages, and prerequisites;
- staged installs into content-addressed release directories and an atomic `current` link;
- systemd unit templates and explicit installation/boot-preparation commands;
- local-only secret-reference resolution into protected state outside every bundle/release;
- loopback health verification, automatic rollback, durable deployment events, and status CLI;
- propagation of the active bundle ID into runtime environment, cell state, and trace events;
- deterministic unit and integration checks for corrupt input and failed-health rollback.

Excluded:

- bundle signing, authenticated publication, artifact download, or remote fleet management;
- Task 022 operator API/UI and Task 023 hardware adapters;
- production-evidence approval, secrets provisioning, functional-safety logic, or arbitrary remote
  health endpoints;
- native package/container construction, which remains outside the Task 006 compiler contract.

## Current state
The clean starting point is `main` at `7c05cb9`, synchronized with `origin/main`. Task 006 is
present at `116bc8b` and freezes canonical manifests, file hashes, target profile, packages, and
prerequisites. Task 012 is present at `a82fa68` and resolves jobs from an active bundle root. Every
numbered Task 001–020 commit is in history, so Task 021's declared prerequisites are merged.

The compiler does not assemble or install bundles. No bundle agent, release state, systemd unit,
health protocol, or local status command exists. Runtime cell state already has a `bundle_id`
parameter, but durable `JobEvent` traces do not yet have an explicit bundle field.

The untouched baseline on 2026-08-11 passes the Makefile-equivalent uv commands: 203 files are
Ruff-formatted, Ruff lint passes, strict mypy passes for 69 Python and 15 Kit sources, all 294
pytest tests pass, and 5 canonical schemas, 6 component schemas, and 22 example YAML documents
validate. Literal `make` commands are unavailable because GNU Make is not installed. The default
uv user cache is sandbox-inaccessible, so local checks use the existing repository `.uv-cache`.

## Design
`cellforge_bundle.agent` owns pure validation and orchestrated installation. A valid source bundle
has `manifest.json`, `checksums.txt`, `config/target-profile.yaml`, `config/agent.json`, the exact
manifest inventory, and only normalized regular files. `checksums.txt` covers every regular file
except itself; the canonical manifest bundle ID and every compiler inventory digest/size are
independently rechecked. Symlinks, traversal, duplicates, undeclared checksum entries, private-key
material, and secret-bearing paths/configuration are rejected.

Local target facts are provisioned outside the bundle and matched exactly against the bundled
profile and manifest. Missing packages/prerequisites and unmet GPU requirements fail before any
runtime stop or release mutation. External prerequisite presence is an explicit local assertion,
not an online lookup.

Installation copies into a unique staging directory, verifies the copy again, then renames it into
`releases/<bundle-id>`. An activation adapter creates a relative temporary symlink and atomically
replaces `current`. Systemd is stopped before the switch and started afterward. The loopback-only
health endpoint must return `status=healthy` and the exact active bundle ID before the activation is
recorded. A failure stops the candidate, restores the previous link and environment, restarts it,
and verifies the previous release; the candidate remains as an immutable inactive release for
diagnosis.

Bundles may declare environment-variable-to-local-secret identifiers in
`config/secret-references.json`; no value syntax exists in that file. Values are read from a local
protected secret store and atomically written with mode 0600 to active state outside releases.
Runtime identity is likewise written outside releases. systemd loads both files. Rollback
regenerates them for the previous bundle, so secret values never enter bundle files or release
directories.

Deployment activation/rollback records are appended durably with both candidate and active bundle
IDs. The canonical ROS `JobEvent` contract gains `bundle_id`; runtime producers populate it from
their configured active bundle, and the durable trace store persists it with a backward-compatible
SQLite migration. This is traceability metadata and standard control, never functional safety.

The package adds PyYAML as a runtime dependency because target profiles are canonical YAML. It is
MIT-licensed, actively maintained, already locked for repository development/job-gateway use, and
can be removed if target profiles move to canonical JSON or the domain loader is split into a
minimal dependency-free parser.

## Work sequence
1. Add strict bundle/target/secret contracts and tests; acceptance: malformed layouts, corrupt
   manifests/files/checksums, incompatible targets, and bundled secret material fail closed.
2. Add staged install, atomic activation, health, rollback, state/event journal, and status models;
   acceptance: successful activation selects the content-addressed release and failed health
   restores the prior known-good bundle.
3. Add CLI and systemd templates/installation plus boot preparation; acceptance: a local status
   command reports active/release/health state and generated runtime environment exposes bundle ID
   without putting secrets in releases.
4. Add explicit bundle identity to runtime trace events and migration/contract tests; acceptance:
   state and trace records preserve the active bundle ID.
5. Update deployment/runtime/security/observability documentation, add the Task 021 integration
   target, run all checks, inspect the full diff, and complete the required Git/GitHub lifecycle.

## Validation
Run:

```text
make lint
make test
make validate-examples
make bundle-agent-check
make ros-build
make ros-test
```

When GNU Make or local ROS 2 Jazzy is unavailable, run the exact Makefile uv recipes locally and
use Ubuntu/Jazzy GitHub Actions as authoritative integration evidence. Focused acceptance checks
must prove checksum corruption rejection, target mismatch refusal before service stop, immutable
versioned install, atomic selection, candidate health failure and verified prior-release rollback,
secret resolution only into local state, status output, and bundle identity in durable traces.

## Risks and rollback
Atomic directory-symlink replacement is a Linux filesystem contract and needs same-filesystem
release/current paths. Windows normally requires elevated symlink permission, so local tests use a
deterministic activation adapter while hosted Linux integration exercises the real link. A crash
between service stop and link switch leaves the old link selected; a crash after switch is detected
by boot preparation/health and remains operator-visible in state. Secret state uses atomic files and
restrictive modes but depends on correct OS ownership/provisioning. Rollback of the code is the
Task 021 commit; installed cells retain immutable releases and can explicitly select their previous
known-good release.

## Progress
- [x] 2026-08-11 — required documents, dependency history, clean Git state, and baseline verified.
- [x] 2026-08-11 — strict bundle validation, compatibility, and secret contracts implemented.
- [x] 2026-08-11 — activation, health, rollback, status, and systemd integration implemented.
- [x] 2026-08-11 — runtime/trace bundle identity and documentation implemented.
- [ ] 2026-08-11 — all local/hosted checks, commit, PR, merge, and main synchronization complete.

## Decisions
- 2026-08-11 — Require checksums to cover every regular bundle file and separately verify the
  compiler manifest inventory; checksum syntax alone is not allowed to replace the content-addressed
  manifest contract.
- 2026-08-11 — Use explicit locally provisioned target facts instead of inferring external SDK or
  package availability from online services; production cells remain offline-capable.
- 2026-08-11 — Resolve named secrets only to an external 0600 environment file and never rewrite an
  immutable release with secret values.
- 2026-08-11 — Require loopback health responses to echo the exact bundle ID so an old or unrelated
  process cannot make a candidate appear healthy.
- 2026-08-11 — Extend canonical trace events with bundle identity because payload-only conventions
  cannot guarantee the system-wide observability contract.
- 2026-08-11 — Treat the `JobEvent` field addition as an intentional runtime interface revision:
  every ROS package in a release must be rebuilt together, while the durable SQLite store migrates
  existing rows with an empty bundle identity and preserves all data.
- 2026-08-11 — Reject any content file omitted from the manifest inventory even when it appears in
  `checksums.txt`; every installed byte must contribute to the content-addressed bundle ID.
- 2026-08-11 — Serialize mutating commands with a nonblocking OS file lock and make explicit
  rollback health-checked and reversible to the current release if the requested prior release is
  no longer healthy.

## Results
The bundle package now contains strict verification, target preflight, versioned read-only release
installation, an atomic activation abstraction with a production relative-symlink implementation,
systemd lifecycle/templates, exact-bundle loopback health, automatic and explicit rollback, local
secret resolution, durable deployment events, and human/JSON status output. Runtime bundle identity
defaults from systemd environment into state, supervisor, motion, and canonical/durable trace
events. The SQLite trace schema migrates existing stores without losing rows.

Local direct Makefile equivalents pass: Ruff format and lint over 208 files, strict mypy over 72
Python and 15 Kit sources, 308 pytest tests, validation of 5 canonical schemas/6 component schemas/
22 example YAML documents, and the Task 021 static integration contract. The focused Task 021 suite
passes 106 tests. One real directory-symlink test is skipped locally because Windows requires an
elevated symlink privilege; it is enabled on hosted Linux. Literal Make, local ROS 2 Jazzy,
clang-format, Docker Linux, WSL, and a running systemd instance are unavailable on this host. Hosted
Ubuntu/Jazzy CI first exposed platform-specific mypy resolution of the guarded `msvcrt` import;
both OS lock modules now load dynamically so strict typing is platform-neutral. CI rerun, final
merge, and local-main verification remain.
