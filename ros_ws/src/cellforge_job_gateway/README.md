# CellForge job gateway

`job_gateway` serves `/cell/run_job`, resolves every request against one configured immutable bundle,
persists the frozen record to SQLite, and then forwards the unchanged goal to
`/cell/supervisor/run_job`.

Required parameters are `bundle_root` and an operator-writable `database_path`. Optional parameters
select the manifest and public/internal action names. Production mode accepts only an active
production bundle and an exact `APPROVED` recipe. Simulation accepts the reference `TESTED` recipe.

Idempotency keys are durable. A completed identical request replays the stored result, a conflicting
request is rejected, and any nonterminal record encountered after restart becomes
`gateway.restart.outcome_unknown` instead of being executed again. The final SQLite commit occurs
before the public action result is completed.

These checks are standard-control admission rules. They neither replace nor override independent
safety-rated protection.
