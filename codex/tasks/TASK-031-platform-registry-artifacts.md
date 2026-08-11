> Follow `AGENTS.md`. Create an ExecPlan. Do not implement unrelated later tasks.

# TASK-031 — Platform registry and artifacts

## Goal
Provide central, authenticated engineering metadata and content-addressed artifact services.

## Deliverables
- versioned FastAPI service with PostgreSQL models/migrations for components, projects, recipes, bundles, and artifact metadata;
- Git-backed source indexing and immutable released records;
- filesystem test backend and S3-compatible production artifact backend;
- component publication, semantic-version conflict, support, license, and deprecation workflows;
- OIDC JWT validation and role mapping, with development auth prohibited in production;
- no platform endpoint for robot joints, equipment commands, or safety control.

## Acceptance
- components and bundles publish, resolve, download, and verify by content digest;
- conflicting/invalid releases and unauthorized mutations fail closed;
- database migrations are reversible and tested from an empty and prior schema;
- a total platform outage does not interrupt the local cell runtime.
