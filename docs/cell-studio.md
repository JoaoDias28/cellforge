# Cell Studio

## 1. Application shell

Cell Studio is implemented as a set of Omniverse Kit extensions running inside Isaac Sim. Keep domain logic in normal Python packages so it can be tested without launching Kit.

Suggested extensions:

```text
cellforge.core             project and service wiring
cellforge.component_browser
cellforge.scene_authoring
cellforge.connections
cellforge.task_editor
cellforge.recipe_editor
cellforge.validation
cellforge.simulation
cellforge.deployment
cellforge.evidence
```

## 2. User workflow

### Create project

- choose **Blank**, **Pen engraving**, or **Two-part kitting** from the guided launcher;
- choose the requested schema version, destination, display name, and any genuinely required
  explicit choices;
- review a deterministic in-memory skeleton containing every generated relative path, schema
  version, cell/component IDs, aliases, defaults, validation findings, and exact SHA-256 hashes;
- confirm **Save** only after the preview is acceptable. Preview, Cancel, and close-without-Save
  do not write the destination or mutate a source example;
- open the saved project through the existing validator and paired YAML/USD identity checks.

Guided projects begin in simulation-only mode. The launcher never chooses a physical target,
recipe, scenario, component, or safety dependency when the request is ambiguous. Template IDs
and canonical example component IDs are retained where the existing simulation contracts require
them; blank-project IDs are allocated from the explicit deterministic seed and never from the
display name.

### Add components

- search registry by type, manufacturer, capability, support level, or simulation level;
- preview model and metadata;
- place component instance;
- select variant;
- configure required values;
- record immutable type/version reference.

### Attach mechanically

- choose source and target mount ports;
- preview transform and adapter requirement;
- create USD parent/reference or constrained transform;
- write connection to `cell.yaml`;
- run collision and payload validation.

### Connect interfaces

Use separate graph layers for:

- capabilities/ROS;
- industrial I/O;
- modeled safety dependencies.

The UI should never make ordinary ROS and safety connections visually indistinguishable.

### Compose task

- browse installed skills;
- drag behavior-tree nodes;
- map typed ports;
- configure retry/timeout decorators;
- validate required capabilities;
- save canonical BehaviorTree.CPP XML plus editor layout metadata.

### Configure recipes

- render forms from schema;
- show units and limits;
- validate compatibility with selected component versions;
- prohibit direct editing of released versions;
- attach simulation evidence before approval workflow.

### Simulate and validate

- start/stop/reset/step;
- choose scenario;
- inject faults;
- visualize frames, collision geometry, planned path, and device states;
- compare expected and actual event timeline;
- save evidence.

### Build deployment

- select target profile;
- resolve package/adapter set;
- show changes from current deployed bundle;
- run required validations/tests;
- generate immutable bundle.

## 3. UI panels

### Project panel

Project identity, branch/revision, schema version, validation summary, dirty state.

### Component browser

Search, filters, support badges, licenses, simulation/hardware status, compatibility warnings.

### Inspector

Selected instance configuration, frames, mounts, capabilities, network/I/O properties, calibration references.

### Connection graph

Typed nodes and edges with validation. Use generated IDs, not display names, as persistence keys.

### Task editor

Behavior-tree graph, blackboard/port mappings, node documentation, simulation breakpoints, runtime monitoring.

### Recipe editor

Schema-driven forms with units, ranges, approval state, diff, and evidence links.

### Validation panel

Grouped errors by schema, spatial, capability, task, recipe, target, safety review, and evidence.

### Simulation panel

Scenario controls, seed, speed, faults, sensors, result summary, timeline.

### Deployment panel

Target, package plan, bundle manifest, hash, install status, rollback candidate.

## 4. Studio internal interfaces

The extension calls a local application service layer rather than editing YAML directly from every widget.

Core commands:

- `CreateProject`
- `OpenProject`
- `PreviewProject`
- `ConfirmProjectSave`
- `CancelProjectDraft`
- `AddComponentInstance`
- `RemoveComponentInstance`
- `SetComponentVariant`
- `SetComponentConfiguration`
- `AttachMechanicalPorts`
- `ConnectLogicalPorts`
- `UpdateTaskDefinition`
- `CreateRecipeVersion`
- `RunValidation`
- `RunScenario`
- `BuildDeploymentBundle`

Commands are undoable where possible and produce domain events. USD changes and `cell.yaml` changes commit as one logical transaction.

## 5. Headless-first requirement

Before the GUI implements an operation, the same operation should exist through `cellforge-cli` or a pure application service. This prevents business rules from becoming trapped in UI callbacks and lets Codex build/test most features without a GPU.

## 6. Initial 3D scope

The MVP does not need a general CAD editor. It needs:

- transform components;
- snap compatible mounts;
- set variants;
- visualize collisions and frames;
- author simple passive primitives;
- import supported USD assets;
- save layer composition;
- run simulation.

Complex geometry modification remains in external CAD/DCC tools.

## 7. Isaac Sim 6 extension shell

Task 014 provides the `cellforge.studio` extension under `src/kit/cellforge.studio`. From an Isaac
Sim 6 installation, launch the interactive shell from the repository root with an absolute
extension folder path:

```bash
./isaac-sim.sh --ext-folder /absolute/path/to/cellforge/src/kit --enable cellforge.studio
```

For the Isaac Sim 6 pip distribution, the equivalent experience command is:

```bash
isaacsim isaacsim.exp.full --ext-folder /absolute/path/to/cellforge/src/kit --enable cellforge.studio
```

Run the lifecycle acceptance probe headlessly on Linux with:

```bash
./isaac-sim.sh --no-window \
  --ext-folder /absolute/path/to/cellforge/src/kit \
  --enable cellforge.studio \
  --exec /absolute/path/to/cellforge/scripts/verify_kit_extension.py
```

On Windows, use `isaac-sim.bat` with the same arguments. The probe verifies activation, all three
windows, and immediate deactivation before exiting. The pure host-independent checks are:

```bash
make kit-extension-check
```

The shell starts with no selected project and does not read or modify project files. Project paths
are inspected only after the user chooses **Open / Refresh**. The Kit callback delegates to the
pure application service, which in turn reuses Task 004 project validation and inspection.
Missing CellForge backend packages or schemas produce an actionable panel state instead of blocking
extension startup.

Task 039 adds the guided Create/Open/Review flow behind the same service boundary. Create and
Preview retain all candidate bytes in memory and expose a versioned diagnostic preview at
`schemas/studio_project_preview.schema.json`; the preview is not a third source of truth. Only
`ConfirmProjectSave` with the current preview confirmation is allowed to create a destination.
New projects are validated in a sibling staging tree and materialized through the existing
paired project validator and Task 015 recovery-journal transaction. Existing project edits use
the same recovery boundary.

## 8. Project and scene round trip

Task 015 adds explicit **Create**, **Open / Refresh**, and **Save** commands. Opening a project and
editing its in-memory buffers do not write project files. Dirty state is derived by comparing the
working buffers with the exact text last opened or successfully saved; only **Save** replaces an
existing `cell.yaml` and scene.

Every component prim authors a namespaced `cellforge:instanceId` string equal to the immutable
component instance ID in `cell.yaml`. The application service validates the two canonical artifacts
together and returns structured findings for missing prims, missing or mismatched IDs, duplicate
operational or scene IDs, and unreferenced tagged prims. UI callbacks render those findings but do
not implement domain or spatial validation.

Save validates both candidates first. It then writes a `.cellforge-save-recovery.json` journal with
the previous canonical bytes, fsyncs temporary candidates, and atomically replaces each file. A
replacement failure restores the previous pair. A journal retained by abrupt process termination is
resolved only by an explicit save/recovery operation, so ordinary open remains read-only.

The deterministic non-Kit acceptance check is:

```bash
make studio-project-scene-check
```

Run the Isaac Sim 6/OpenUSD integration probe headlessly from the repository root on Linux with:

```bash
./isaac-sim.sh --no-window \
  --ext-folder /absolute/path/to/cellforge/src/kit \
  --enable cellforge.studio \
  --exec /absolute/path/to/cellforge/scripts/verify_kit_project_scene.py
```

On Windows, use:

```powershell
isaac-sim.bat --no-window `
  --ext-folder C:\absolute\path\to\cellforge\src\kit `
  --enable cellforge.studio `
  --exec C:\absolute\path\to\cellforge\scripts\verify_kit_project_scene.py
```

The Isaac Sim Python environment must contain the locked CellForge Python workspace, as required by
the extension backend. Text USDA stages round-trip in deterministic non-Kit tests; binary USD stage
inspection requires the Isaac Sim 6 OpenUSD runtime.

## 9. Component browser and placement

Task 016 adds a project-local component browser backed by the Task 005 filesystem registry. Kind,
capability, support-level, and simulation-level filters are conjunctive. Detail records show exact
type/version identity, declared capabilities, variants, support/fidelity, compatible execution
modes, and clear production warnings. The browser reuses the domain resolver's compatibility
policy; Kit widgets do not reproduce those rules.

Placement generates an immutable UUID-derived component instance ID, accepts an editable stable
alias and one selection for every declared variant set, adds the operational instance to
`cell.yaml`, and authors a referenced USD Xform with the same `cellforge:instanceId`. Placement and
removal update only the in-memory paired buffers until **Save** invokes Task 015's validation and
transactional replacement. Undo and redo restore complete YAML/USD buffer pairs.

Removing an instance with incident connections is refused until the engineer explicitly chooses
to cancel or remove those connections with the instance. Modeled safety edges follow this graph
editing rule but remain descriptive only; Cell Studio does not implement a safety function.

The deterministic non-Kit Task 016 acceptance check is:

```bash
make studio-component-placement-check
```

Run the Isaac Sim 6/OpenUSD placement probe headlessly from the repository root on Linux with:

```bash
./isaac-sim.sh --no-window \
  --ext-folder /absolute/path/to/cellforge/src/kit \
  --enable cellforge.studio \
  --exec /absolute/path/to/cellforge/scripts/verify_kit_component_placement.py
```

On Windows, use:

```powershell
isaac-sim.bat --no-window `
  --ext-folder C:\absolute\path\to\cellforge\src\kit `
  --enable cellforge.studio `
  --exec C:\absolute\path\to\cellforge\scripts\verify_kit_component_placement.py
```

The Isaac Sim environment must contain the locked CellForge Python workspace. The deterministic
fallback covers text USDA editing and cross-reference validation; the Isaac command verifies
OpenUSD composition of the authored component reference. Task 017 builds on this placement contract.

## 10. Connection authoring and validation

Task 017 adds a pure connection-authoring service and a dockable typed connection graph. Ports and
edges are grouped as mechanical, software, industrial I/O, or modeled safety. Stable component
instance IDs and port IDs are persistence keys; aliases are display-only. Candidate connections are
submitted to the Task 005 domain resolver, so endpoint kind, direction, and type rules are not
duplicated in Kit callbacks.

Mechanical ports declare a component-local row-major 4x4 `metadata.snap_transform`. A compatible preview
computes the target transform and proposed USD prim path without changing either canonical source.
Applying the connection reparents the target component prim, authors the snap transform, updates
affected `usd_prim` paths, and adds the `cell.yaml` edge as one undoable paired-buffer edit. Missing,
singular, or uneditable spatial data fails closed.

Software and industrial-I/O edges update only the canonical operational graph. Modeled-safety edges
are colored and labeled separately, persist `modeled_only: true`, and are always reported as
non-executable. They are engineering-review metadata only; Cell Studio does not implement, replace,
or authorize any safety-rated function or ordinary executable wiring.

The deterministic non-Kit acceptance check is:

```bash
make studio-connections-check
```

Run the Isaac Sim 6/OpenUSD connection probe headlessly from the repository root on Linux with:

```bash
./isaac-sim.sh --no-window \
  --ext-folder /absolute/path/to/cellforge/src/kit \
  --enable cellforge.studio \
  --exec /absolute/path/to/cellforge/scripts/verify_kit_connections.py
```

On Windows, use:

```powershell
isaac-sim.bat --no-window `
  --ext-folder C:\absolute\path\to\cellforge\src\kit `
  --enable cellforge.studio `
  --exec C:\absolute\path\to\cellforge\scripts\verify_kit_connections.py
```

The Isaac Sim environment must contain the locked CellForge Python workspace. This probe composes
the authored hierarchy, metadata, and transform through OpenUSD; deterministic non-Kit tests cover
invalid inputs and filesystem-independent failure paths.

### 10.1 Visual connection canvas contract

Task 042 exposes the connection canvas through the application-service commands
`PreviewCellConnection`, `StageCellConnection`, `RemoveCellConnection`, and
`ValidateCellConnections`. The returned DTOs separate the mechanical, software/capability,
industrial-I/O, and modeled-safety layers, and provide a searchable port palette, endpoint
highlighting, deterministic edge IDs, layout positions, route points, findings, and candidate
SHA-256 hashes. Canvas coordinates, aliases, selection, and routes are derived presentation
metadata; canonical edges use component instance IDs, port IDs, and kind, while presentation
endpoint keys include the layer so same-named ports cannot collide.

Preview returns a no-write candidate. Mechanical staging changes the `cell.yaml` component prim,
USD reparent, snap transform, and connection edge as one in-memory pair. Logical and industrial
I/O staging changes only the operational graph. Explicit Save is still required and uses the
existing transactional recovery journal, so a replacement failure restores both canonical files.
Removal reverses only an unambiguous recorded mechanical reparent and reports a review warning for
modeled-safety edges. Existing mechanical edges are revalidated non-mutatively on browse and Save.
Mechanical authoring refuses to overwrite pre-existing transform properties; removal requires the
recorded source/target paths, exact authored property block, and matching `cellforge:mechanicalConnection`
marker, otherwise it fails closed. Rendered ports and edges are selectable and populate the preview
form without moving domain compatibility rules into UI callbacks.

The safety layer is colored and labeled `MODELED SAFETY (NON-EXECUTABLE)`. Its optional
`modeled_only: true` marker is schema-constrained to `kind: safety`; the canvas never turns a
safety edge into an executable connection, authorizes a process, or replaces independent rated
hardware. The deterministic non-Kit Task 042 check is:

```bash
make studio-visual-connections-check
```

When Isaac Sim is installed, run the corresponding OpenUSD probe with
`scripts/verify_kit_visual_connections.py` using the same headless `isaac-sim(.bat)` invocation
shown above.

## 11. Simulation and scenario control

Task 018 adds the **CellForge Simulation** panel. Its callbacks delegate configure, reset, start,
pause, step, fault, and finalize commands to a pure `SimulationApplication`, which uses the typed
ROS 2 simulation services. Widgets do not manipulate the timeline, stage, adapters, scenario
assertions, or evidence directly.

The extension hosts those services in Kit and spins the bridge once per application update on the
main thread; external ROS callbacks never manipulate Isaac APIs from a worker process or UI widget.

Configuration selects the canonical project directory and one scenario declared by its
`cell.yaml`. Simulated adapters register their actual fidelity and canonical capability endpoints.
The panel shows unavailable and failure states explicitly. Finalization stores normalized trace and
assertion evidence containing the exact seed and canonical YAML/USD hashes.

The deterministic non-Kit acceptance check is:

```bash
make studio-simulation-check
```

The Isaac Sim 6 headless command is documented in `docs/simulation.md`. L0 control evidence does not
claim physics, perception, process quality, hardware validation, or functional-safety enforcement.

## 12. Spatial configuration and calibration

Task 028 adds a viewport-neutral spatial configuration service behind Studio controls. An engineer
selects an immutable component instance ID, can inspect its declared frames and collision asset, and
can apply a finite non-singular 4x4 transform to its USD Xform. Configuration and variants are
edited only through the component JSON schema and declared manifest variant sets. The spatial browser
feeds the viewport selection controls with immutable instance IDs, transforms, frame IDs, and the
declared collision asset. The service validates the candidate `cell.yaml` and USDA pair before
returning an in-memory edit; **Save** remains the transactional persistence boundary and undo/redo
restores the complete pair.

Calibration creation/import stages a canonical JSON artifact under `calibration/`, validates the
canonical schema, checks its immutable digest and expiry, and requires a matching immutable
component instance ID. The artifact path is bound in both the cell and the component's
`calibration_refs` in the same candidate. It remains engineering data only and has no safety
authority. Reopening validates every declared artifact, including its canonical encoding, digest,
expiry, path, and component binding.

The deterministic acceptance check is:

```bash
make studio-spatial-configuration-check
```

The supported Isaac Sim 6 headless interaction/OpenUSD check is:

```bash
./isaac-sim.sh --no-window \
  --ext-folder /absolute/path/to/cellforge/src/kit \
  --enable cellforge.studio \
  --exec /absolute/path/to/cellforge/scripts/verify_kit_spatial_configuration.py
```

The deterministic check validates contracts but does not substitute for the actual Kit viewport and
OpenUSD interaction check.

## 13. Task authoring, recipe management, and deployment evidence

Tasks 029 and 030 complete the Studio authoring and deployment workflow:

- **Task authoring:** inspects and edits BehaviorTree.CPP XML with realtime port matching and
  frozen node registration validation, preventing malformed task trees before compilation.
- **Recipe editor:** dynamic schema-driven form editing for versioned recipes, supporting
  compatibility validation, product SKUs, process limits, and approval status tracking.
- **Scenario runner & replay:** deterministic scenario execution with seed control, fault injection
  scheduling, trace event capturing, and exact seed replay verification.
- **Fidelity guard:** strictly enforces simulation fidelity labels, refusing to label L0 or CPU-only
  execution as L2 without active CUDA GPU and PhysX execution.
- **Signed bundle assembly:** exports immutable deployment bundles with detached Ed25519 signatures,
  checksum inventories, and deployment profile target preflight verification.
- **Software release qualification:** automated qualification workflow proving that all Studio
  outputs feed directly into deterministic L0/L2 runtime execution.

## 14. Studio readiness guidance

Task 040 adds the **CellForge Readiness** panel and the pure `EvaluateStudioReadiness` application
service. It evaluates the selected canonical project through the existing project validator,
registry/resolver, task, recipe, scenario, calibration, deployment, evidence, and simulation
fidelity services. Each result has a deterministic check ID, status (`pass`, `blocked`, `advisory`,
or `unavailable`), severity, source reference, validator link, remediation ID, and evidence
references. The normalized report is diagnostic/evidence data only and is validated against
`schemas/studio_readiness_report.schema.json`; it is not a Cell Runtime source.

The panel keeps requested and actually observed fidelity separate. The CPU/mock path is explicitly
L0. An L2/L3 result requires an available backend and proof of the corresponding Isaac Sim, GPU,
and actual PhysX execution; missing capability is `unavailable`, never a synthetic pass. Modeled
safety dependencies are shown in a separate **safety review** category. Readiness is engineering
guidance, not functional-safety validation, commissioning approval, physical authorization, or a
replacement for rated hardware and independent safety review.

Remediation actions are preview-only. They may stage in-memory `ProjectContents` and expose a
confirmation token, but they cannot write `cell.yaml`, the paired USDA scene, BehaviorTree.CPP XML,
recipes, scenarios, or diagnostic reports. **Save after preview** re-evaluates the complete
candidate and delegates persistence to the existing Task 015/039 transactional paired-artifact
boundary. Validation failures and injected replacement failures preserve the previous canonical
source hashes.

The deterministic non-Kit acceptance check is:

```bash
make studio-readiness-check
```

If Make is unavailable, run the locked command bodies from the target:

```bash
uv sync --locked --all-packages
uv run --frozen pytest src/kit/cellforge.studio/tests/test_readiness.py
uv run --frozen python scripts/verify_studio_readiness.py
```

The Isaac Sim probe remains an integration check when the Kit runtime is installed; the pure
readiness report must display that integration as unavailable when it cannot prove higher-fidelity
execution.

## 15. Schema-driven authoring

Task 041 adds one pure authoring service for cell documents, component configuration schemas,
recipes, and simulation scenarios. `BuildSchemaForm` resolves Draft 2020-12 schemas and local
`$ref` values into immutable `SchemaFormModel` data. `UpdateSchemaForm`, `PreviewSourceEdit`, and
`MergeSourceEdit` return new in-memory models or candidates; none of these commands write a source.
`SaveAuthoringCandidate` requires the reviewed confirmation token and delegates project saves to the
existing paired validation and recovery-journal transaction.

Schemas may add an `x-cellforge` annotation object with `label`, `group`, integer `order`, `unit`,
`help`, `advanced`, and `generated`. These are presentation hints only. Unknown annotation members
are ignored. Unknown validation keywords are reported as errors, so a schema author cannot
accidentally rely on a keyword the authoring service does not implement. Required multi-value enums
and other ambiguous choices remain explicit `AuthoringChoice` records until the caller selects one.
IDs and authoring paths use a stable allocator seed; defaults, field ordering, groups, exact JSON
Pointer diffs, canonical output, and candidate hashes are deterministic.

The reusable renderer only maps service DTOs to widget-neutral fields. It does not import domain
models, interpret schema keywords, choose defaults, enforce recipe lifecycle policy, or implement
safety behavior. Released recipe versions remain immutable, and scenario seed, fault schedule, and
requested fidelity stay explicit in the candidate. Unknown material or unapproved recipe state never
authorizes a physical process; rated safety hardware and independent safety review remain outside
Cell Studio.

No-op previews preserve original source bytes. When a meaningful form edit requires regenerated YAML
or JSON, the candidate carries an explicit formatting/order warning and the exact candidate text so
comments and ordering are never silently rewritten. Save-after-preview rechecks the source hash and
full project validation; stale, invalid, ambiguous, unavailable-backend, and transactional-failure
paths leave canonical files unchanged.

The deterministic non-Kit acceptance check is:

```bash
make studio-schema-authoring-check
```

If Make is unavailable, run the locked command bodies from the target:

```bash
uv sync --locked --all-packages
uv run --frozen pytest src/kit/cellforge.studio/tests/test_schema_authoring.py
uv run --frozen python scripts/verify_studio_schema_authoring.py
```

The optional Isaac Sim headless interaction probe is unavailable unless the Kit runtime is
installed; the pure authoring contract does not claim viewport, OpenUSD, physics, hardware, or
functional-safety evidence.
