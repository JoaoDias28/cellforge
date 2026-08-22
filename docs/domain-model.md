# Domain model

## 1. Identifiers

Use stable, lowercase, URL-safe identifiers.

- component type: `manufacturer.model.capability-family`
- component version: semantic version
- component instance: generated UUID plus optional alias
- cell: UUID plus human name
- capability contract: reverse-domain or project namespace plus semantic version
- recipe: UUID with monotonically increasing immutable versions
- deployment bundle: SHA-256 content digest

Human names may change. Stable IDs may not.

## 2. Component type versus instance

A component type describes a reusable supported product, such as a specific camera model or generic simulated fixture. A component instance represents one item in a cell project with a transform, configuration, network address, calibration reference, and selected adapter.

## 3. Port types

### Mechanical ports

Define named mount frames and compatibility tags.

Examples:

- `iso_9409_1_50_4_m6`
- `camera_m4_pattern_30x30`
- `fixture_table_tslot_8`

Mechanical compatibility is advisory until verified by engineering data. Adapters can bridge incompatible tags.

### Software ports

Declare ROS topic, service, or action contracts by capability rather than absolute runtime name. Names are generated per instance.

### Industrial I/O ports

Declare direction, logical type, electrical/protocol constraints, normal state, debounce, and diagnostic mapping.

### Modeled safety ports

Declare required safety status or rated-output dependencies for review and validation. These are not ordinary executable connections.

Connections use immutable component instance IDs, declared port IDs, and an explicit connection kind
as canonical endpoints. A generated edge ID is a full digest of that unambiguous tuple; aliases and
visual graph layout never participate in identity. A safety connection may carry the optional
`modeled_only: true` marker, but that marker is descriptive review metadata and cannot authorize a
physical process or replace rated safety hardware.

## 4. Frames

Every component may declare frames:

- root frame;
- mount frames;
- tool center points;
- sensor optical frames;
- process frames;
- calibration targets;
- product reference frames.

A cell connection can establish a fixed transform by mechanical attachment. Dynamic transforms are provided by simulation or hardware state.

## 5. Capabilities

A capability is a stable logical operation with a versioned contract. A component may implement one or more capabilities. A skill may depend on capabilities without naming a manufacturer.

Capability implementation metadata includes:

- contract ID, exact semantic version, and a matching
  `cellforge://capabilities/<contract>/<version>` definition URI;
- endpoint mapping;
- supported modes;
- limits;
- fault mapping;
- quality/support level;
- simulation fidelity.

## 6. Skill

A skill is reusable robot-cell behavior implemented as a ROS action server or behavior-tree subtree.

Examples:

- pick from known tray;
- load fixture;
- locate product;
- execute machine cycle;
- inspect engraving;
- route reject.

A skill declares required capabilities, parameters, preconditions, outputs, and failure codes.

Canonical Draft 2020-12 schemas now cover capability contracts, skills, fault catalogs,
calibration artifacts, and evidence records in addition to project documents. A component
capability declaration is invalid unless its definition URI names the declared contract/version.

## 7. Cell project

A cell project is a graph of component instances plus:

- spatial scene reference;
- connections;
- task definitions;
- recipe schema bindings;
- calibration bindings;
- simulation scenarios;
- deployment target profiles;
- evidence requirements.

## 8. Recipe

Recipe lifecycle:

```text
DRAFT → VALIDATED → TESTED → APPROVED → RETIRED
```

Transitions are append-only records. Editing an approved recipe creates a new draft version.

## 9. Calibration

Calibration is a first-class immutable artifact with:

- type;
- source and target frame IDs;
- algorithm and version;
- date;
- operator;
- environment conditions where relevant;
- residual/error metrics;
- raw evidence reference;
- valid hardware serial numbers;
- expiry or revalidation rule;
- signed checksum.

Examples include camera intrinsics, hand-eye transform, tool center point, fixture frame, and laser focus offset.

## 10. Scenario

A simulation scenario defines:

- initial component state;
- product variant and pose distribution;
- lighting and sensor variation;
- injected fault schedule;
- expected outcome;
- maximum cycle time;
- required events and forbidden events;
- random seed or seed range.

## 11. Evidence

Evidence types:

- schema validation report;
- simulation scenario result;
- Monte Carlo summary;
- calibration report;
- hardware bench test;
- commissioning checklist;
- production acceptance test;
- safety review attachment.

A deployment policy declares which evidence types and freshness are required.
