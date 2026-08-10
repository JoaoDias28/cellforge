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
are inspected only after the user chooses **Open / Refresh (read-only)**. The Kit callback delegates
to the pure application service, which in turn reuses Task 004 project validation and inspection.
Missing CellForge backend packages or schemas produce an actionable panel state instead of blocking
extension startup. No project/scene editing is implemented until Task 015.
