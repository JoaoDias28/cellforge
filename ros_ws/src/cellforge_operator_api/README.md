# cellforge_operator_api

This ROS 2 Jazzy package serves the production cell's local, loopback-only operator API and minimal
same-origin web page. It reads canonical cell state and trace data and exposes only fixed typed
runtime controls. It has no platform-server or internet dependency.

## Routes

- `GET /health`
- `GET /api/v1/status`
- `GET /api/v1/jobs/active`
- `GET /api/v1/faults`
- `GET /api/v1/identity`
- `GET /api/v1/traces/{trace_id}/summary`
- `GET /api/v1/recovery-actions`
- `POST /api/v1/jobs`
- `POST /api/v1/jobs/{job_id}/cancel`
- `POST /api/v1/recovery-actions/{action_id}`

API routes require a local bearer token. The token file stores SHA-256 digests, principal IDs, and
roles; it is provisioned under `/etc/cellforge` and never enters a bundle. Viewer may read,
operator may submit/cancel jobs and use operator-approved acknowledgements, and maintainer is the
minimum role for maintenance actions. The runtime independently validates every command.

The recovery catalog is immutable bundle content. It maps stable fault codes to semantic action
kinds, instructions, confirmation text, and minimum roles. It cannot contain ROS graph names,
executables, commands, or vendor calls. The ROS bridge itself contains only fixed `/cell/state`,
`/events/job`, `/cell/run_job`, and `/cell/operator_action` contracts.

Every mutation records a durable SQLite `REQUESTED` event before dispatch and a terminal outcome
before response. Denials, invalid input, failures, timeouts, and caller cancellation are recorded.
If the audit journal cannot record the request, dispatch is refused.

## Local configuration

Required bundle-agent environment: `CELLFORGE_BUNDLE_ROOT` and `CELLFORGE_BUNDLE_ID`. Optional
cell-local paths are `CELLFORGE_OPERATOR_AUTH`, `CELLFORGE_OPERATOR_AUDIT`, and
`CELLFORGE_TRACE_DATABASE`. `CELLFORGE_RECOVERY_CATALOG` must resolve inside the active bundle.
The server rejects non-loopback `CELLFORGE_OPERATOR_HOST` addresses.

FastAPI is MIT licensed and uvicorn is BSD-3-Clause licensed; both are actively maintained. They
provide only the ASGI/HTTP layer and can be removed by replacing `api.py` and `main.py` while
preserving the pure authorization, audit, recovery, and runtime-port contracts.

Displayed safety state is read-only standard-control information. This package does not reset,
bypass, or implement functional safety; independent rated hardware remains authoritative.
