# Cell Studio

This Isaac Sim 6 extension provides dockable project, component-browser, validation, and session-log
panels. It is an engineering tool, not a production runtime or functional-safety system. Opening
the extension starts with no project selected and performs no project file reads or writes.

Project selection invokes the pure application service and existing CellForge CLI/domain backend.
The UI renders backend findings; it does not implement schema or domain validation rules. If the
CellForge Python packages or canonical schemas are unavailable in Isaac Sim's Python environment,
the panels remain usable and explain how to restore the backend.

Task 015 adds explicit project create/open/save commands, in-memory dirty tracking, linked
`cellforge:instanceId` validation across `cell.yaml` and USD, and recovery-journal-backed saves.
Opening and in-memory edits remain read-only until the engineer selects **Save**.

Task 016 adds filtered registry browsing, component compatibility details, linked YAML/USD
placement with immutable shared IDs and selected variants, explicit connection resolution on
removal, and paired-buffer undo/redo. Production support warnings are engineering information only;
they do not authorize physical operation or implement functional safety.
