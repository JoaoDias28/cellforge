# Cell Studio

This Isaac Sim 6 extension provides dockable project, component-browser, validation, and session-log
panels. It is an engineering tool, not a production runtime or functional-safety system. Opening
the extension starts with no project selected and performs no project file reads or writes.

Project selection invokes the pure application service and existing CellForge CLI/domain backend.
The UI renders backend findings; it does not implement schema or domain validation rules. If the
CellForge Python packages or canonical schemas are unavailable in Isaac Sim's Python environment,
the panels remain usable and explain how to restore the backend.

Task 039 adds a guided Create/Open/Review flow for the blank, pen, and kitting starting points.
The launcher produces an in-memory deterministic preview of paths, IDs, schema versions, findings,
and SHA-256 hashes. Preview and Cancel are read-only; only an explicit ConfirmProjectSave persists
the canonical `cell.yaml`, USD scene, BehaviorTree.CPP XML, recipe references, and scenario
references. Guided projects start in simulation-only mode and never implement or certify
independent functional safety.

Task 015 adds explicit project create/open/save commands, in-memory dirty tracking, linked
`cellforge:instanceId` validation across `cell.yaml` and USD, and recovery-journal-backed saves.
Opening and in-memory edits remain read-only until the engineer selects **Save**.

Task 016 adds filtered registry browsing, component compatibility details, linked YAML/USD
placement with immutable shared IDs and selected variants, explicit connection resolution on
removal, and paired-buffer undo/redo. Production support warnings are engineering information only;
they do not authorize physical operation or implement functional safety.

Task 017 adds a typed port browser and connection graph for mechanical, software, industrial-I/O,
and modeled-safety edges. Candidate edges are validated by the domain resolver. Mechanical snap
previews use declared port transforms and apply `cell.yaml` plus USD changes as one undoable edit.
Modeled-safety dependencies have distinct styling and remain non-executable engineering metadata;
they do not implement or authorize any safety-rated function.

Task 018 adds a ROS-backed simulation panel for deterministic reset/start/pause/step, scenario
setup, test fault injection, trace assertions, and evidence. It reports fidelity limits and does not
provide functional-safety enforcement.

Task 040 adds the readiness guidance panel. Its pure `EvaluateStudioReadiness` service reuses the
canonical validators and registries to show source-linked pass, blocked, advisory, and unavailable
checks for project pairing, schemas, components, ports, assets, tasks, recipes, scenarios,
adapters, fidelity, calibration, evidence, and deployment prerequisites. Normalized reports are
diagnostic only; L0 remains explicitly L0 and unavailable fidelity is never promoted. Modeled safety
appears under a separate safety-review category and never authorizes physical operation or claims
functional-safety validation. Remediation previews are in-memory only; explicit Save after preview
is the sole path to the existing transactional paired-artifact boundary.
