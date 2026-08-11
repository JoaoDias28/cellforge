# Safety and security

## 1. Functional safety boundary

CellForge is standard control and engineering software. It is not a safety-rated control system.

Independent rated hardware must enforce all required protective functions, including as applicable:

- emergency stop;
- protective stop;
- guard-door monitoring and locking;
- safe speed/position functions;
- laser emission enable;
- extraction interlock;
- reset and restart behavior.

CellForge may consume safety-status outputs and refuse to start. Loss of CellForge must not defeat a protective function.

## 2. Hazardous command rules

- An AI output is never sufficient authorization for a hazardous process.
- A recipe may select only preapproved process programs and bounded parameters.
- Unknown material or product identity blocks physical processing.
- Communication uncertainty after a hazardous command creates an explicit recovery state.
- Maintenance commands require local enabling and role authorization.
- No API endpoint provides “disable interlock” or equivalent behavior.

## 3. Network zones

```text
Enterprise IT
    │ controlled API boundary
Cell OT network
    │ protocol gateways / adapters
Equipment network

Safety circuit or safety network remains logically and physically independent where required.
```

## 4. Security controls

Initial requirements:

- least-privilege service accounts;
- TLS for platform and enterprise APIs;
- authenticated bundle publication;
- role-based API authorization;
- audit log for recipe approval, deployment, maintenance mode, and manual recovery;
- no secrets in Git;
- dependency and container scanning;
- pinned dependencies and checksums;
- cell firewall allow-list;
- disable unused services;
- offline-capable production.

### 4.1 Bundle-agent secret boundary

Deployment bundles may contain secret identifiers but never secret values. Task 021 rejects secret-
bearing paths, structured password/token/private-key values, private-key material, and symlinks.
The cell's separately provisioned secret store is resolved locally into a mode-0600 environment
file under `/var/lib/cellforge`; that file is not copied into the immutable release. systemd runs
the runtime as the least-privilege `cellforge` account with `NoNewPrivileges`, a read-only system
view, and only CellForge state/log paths writable. These are security and standard-control measures,
not functional-safety enforcement.

### 4.2 Local operator authorization

Task 022 authenticates local bearer tokens against SHA-256 digests in protected cell-local
configuration. Viewer is read-only; operator may submit/cancel jobs and perform explicitly
operator-approved acknowledgement actions; maintainer is required for maintenance entry;
administrator remains subject to the same immutable action catalog and runtime state checks.

All mutation attempts are durably audited before dispatch, including invalid credentials, invalid
input, and insufficient roles. Tokens and submitted job payloads are excluded from audit details.
The service refuses dispatch when the requested-event audit write fails. HTTP and recovery payloads
cannot name ROS endpoints or arbitrary commands, and the server rejects non-loopback bind addresses.
No role or endpoint can disable an interlock, reset rated safety logic, or substitute for local
presence/enabling required by the safety design.

## 5. Supply chain

Every imported component package records:

- source;
- license;
- checksum;
- version;
- modification history;
- security/support owner.

Vendor SDK binaries are referenced as external prerequisites unless redistribution rights are confirmed.

## 6. AI model governance

Each model release records:

- training-data provenance summary;
- intended use and excluded use;
- input/output contract;
- validation dataset;
- performance by relevant product variant;
- confidence threshold;
- deterministic post-validation;
- fallback behavior;
- model file hash.

Model changes create new versioned evidence and cannot silently replace production inference.
