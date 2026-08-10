# Cell Studio

This Isaac Sim 6 extension provides dockable project, validation, and session-log panels. It is an
engineering tool, not a production runtime or functional-safety system. Opening the extension starts
with no project selected and performs no project file reads or writes.

Project selection invokes the pure application service and existing CellForge CLI/domain backend.
The UI renders backend findings; it does not implement schema or domain validation rules. If the
CellForge Python packages or canonical schemas are unavailable in Isaac Sim's Python environment,
the panels remain usable and explain how to restore the backend.

Task 015 adds explicit project create/open/save commands, in-memory dirty tracking, linked
`cellforge:instanceId` validation across `cell.yaml` and USD, and recovery-journal-backed saves.
Opening and in-memory edits remain read-only until the engineer selects **Save**. Component placement
is not part of this extension increment and remains Task 016 scope.
