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

- select template or blank cell;
- choose schema version;
- create Git-friendly project directory;
- initialize USD stage and `cell.yaml`;
- assign cell ID.

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
