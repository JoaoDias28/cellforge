# cellforge-cli

Typed, headless engineering commands for CellForge project scaffolding, validation, inspection,
schema discovery, and canonical example copying.

The package depends only on `cellforge-domain` and the Python standard library. It does not import
ROS, Isaac Sim, FastAPI, vendor SDKs, or production-control services. Validation reports modeled
safety data but does not implement or claim a functional-safety function.

Run `cellforge --help` for command usage. Add `--json` anywhere in a command for a stable JSON
envelope suitable for CI and other tooling. Exit codes are documented in `docs/cli.md`.

Canonical schemas and the pen example are force-included from the repository source trees when a
wheel is built. Editable source checkouts use those same source trees directly.

## Dependencies

No new external dependency is introduced. `cellforge-domain` is the existing internal pure-domain
package. Removing this CLI consists of removing this independent workspace package and its root
quality-gate entries; domain schemas and models remain usable directly.
