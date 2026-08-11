# cellforge-bundle

`cellforge_bundle` compiles an already-authored cell project into a deterministic deployment plan
and canonical manifest. Its local bundle agent verifies, installs, atomically activates, health-
checks, rolls back, and reports immutable releases. It performs no binary/container build,
publication, remote fleet control, or safety function.

The package depends on the pure `cellforge_domain` contracts. The domain package does not import
this application layer. Expected invalid inputs are returned as stable findings in a
`CompilationReport`.

The bundle ID is SHA-256 over canonical UTF-8 JSON for every manifest field except the
self-referential `bundle_id`. The manifest file inventory freezes the exact source content hashes.
Production compilation requires approved recipes and production-qualified hardware adapters, then
fails closed at the explicit evidence-policy placeholder until a real evidence verifier is added.

The agent requires PyYAML 6.x to read canonical target profiles. PyYAML is MIT-licensed, actively
maintained, and already used by CellForge's domain and job-gateway packages. It can be removed when
target profiles become canonical JSON or profile loading moves behind a dependency-free domain
contract.

Systemd templates run the boot-time `prepare-active` guard before the runtime, load bundle identity
and locally resolved secrets from protected state outside releases, and start only the selected
`/opt/cellforge/current` runtime. `cellforge-bundle-agent status --json` is the machine-readable
local status interface.
