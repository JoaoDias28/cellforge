# Deployment

## 1. Target profiles

A target profile declares:

- CPU architecture;
- Ubuntu and ROS versions;
- GPU availability and driver baseline;
- ROS domain/network settings;
- allowed package sources;
- installed vendor SDK prerequisites;
- systemd unit template;
- local storage limits;
- connectivity to enterprise/platform services;
- execution modes permitted.

## 2. Bundle contents

```text
bundle/
├── manifest.json
├── checksums.txt
├── runtime/
│   ├── native packages or workspace install reference
│   ├── containers/
│   └── launch/
├── config/
│   ├── cell.yaml
│   ├── device configs
│   ├── behavior trees
│   ├── target-profile.yaml
│   ├── agent.json
│   └── secret-references.json  names only; optional
├── recipes/
├── calibration/
├── assets/                    only runtime-required assets
├── schemas/
├── scripts/
│   ├── preflight
│   ├── install
│   ├── healthcheck
│   └── rollback
└── evidence-summary.json
```

## 3. Build properties

A bundle build must be:

- reproducible from a Git revision and lock data;
- immutable after creation;
- content-addressed;
- validated before publication;
- traceable to test evidence;
- explicit about external prerequisites not included.

## 4. Activation

Recommended filesystem layout:

```text
/opt/cellforge/releases/<bundle-id>/
/opt/cellforge/current -> releases/<bundle-id>
/var/lib/cellforge/
/var/log/cellforge/
```

Activation procedure:

1. copy to staging;
2. verify checksums and target compatibility;
3. run static configuration checks;
4. stop runtime safely;
5. switch atomic link;
6. start runtime;
7. run health check;
8. mark active or rollback.

### 4.1 Task 021 agent contract

`cellforge-bundle-agent install <bundle>` accepts a directory only when:

- `manifest.json` has its canonical Task 006 SHA-256 bundle ID;
- the manifest inventory digest and size bind every content file except the manifest and its
  derived checksum list;
- sorted `checksums.txt` covers every regular file except itself exactly once;
- every path is normalized, relative, and regular (bundle symlinks are rejected);
- `config/agent.json` selects a valid runtime target and loopback health endpoint;
- `scripts/start-runtime` exists and is executable on the Linux cell target;
- locally provisioned `/etc/cellforge/target.json` exactly matches the target profile and lists
  every required native package and external prerequisite.

The agent copies to a unique staging directory, verifies the copy, and renames it to
`/opt/cellforge/releases/<bundle-id>`. Existing releases are verified and never overwritten. It
stops the currently selected systemd target, atomically replaces the relative `current` symlink,
starts the candidate target, and waits for `{"status":"healthy","bundle_id":"<exact-id>"}` from
the configured loopback endpoint. A failed candidate is stopped and the previous release link,
runtime environment, secrets, service, and health check are restored automatically. Both candidate
and active IDs are written to `/var/lib/cellforge/deployment-events.jsonl`.

`checksums.txt` uses sorted GNU SHA-256 lines (`<64 lowercase hex><two spaces><relative path>`).
`config/agent.json` is intentionally small:

```json
{
  "schema_version": "0.1.0",
  "systemd_unit": "cellforge-runtime.target",
  "health": {
    "url": "http://127.0.0.1:9080/health",
    "timeout_seconds": 30,
    "interval_seconds": 1
  }
}
```

Only an HTTP loopback URL is accepted. Target facts are separately provisioned local assertions,
not copied out of the bundle:

```json
{
  "schema_version": "0.1.0",
  "profile_id": "pen-cell-amd64",
  "platform": {
    "arch": "amd64",
    "os": "ubuntu-24.04",
    "ros_distribution": "jazzy",
    "gpu": {"available": false}
  },
  "native_packages": ["cellforge_supervisor"],
  "external_prerequisites": []
}
```

The local commands are:

```text
cellforge-bundle-agent verify <bundle>
cellforge-bundle-agent install <bundle>
cellforge-bundle-agent status [--json]
cellforge-bundle-agent rollback
cellforge-bundle-agent prepare-active
cellforge-bundle-agent install-systemd
```

`prepare-active` is the systemd boot guard: it rechecks the selected immutable release and local
target, then regenerates runtime environment files before ROS/runtime processes start.

## 5. Secrets

Secrets are never stored in cell source, recipes, or bundles. Target installation resolves secret references from local protected storage.

Task 021 permits only `config/secret-references.json`, whose `environment` map contains environment
variable names and local secret identifiers. Values are read from `/etc/cellforge/secrets` and
written atomically with mode 0600 to `/var/lib/cellforge/secrets.env`. The release remains byte-for-
byte identical to the verified source bundle. Secret-bearing paths, private keys, and sensitive
configuration values cause bundle rejection.

Example reference document (the strings on the right are local identifiers, not values):

```json
{
  "schema_version": "0.1.0",
  "environment": {"LASER_API_TOKEN": "laser/api-token"}
}
```

### 5.1 Operator credentials and recovery catalog

Operator bearer-token digests are separately provisioned in `/etc/cellforge/operator-auth.json`;
raw tokens and token digests are not bundle files or audit fields. The runtime audit journal lives
under `/var/lib/cellforge`. The API binds only to a numeric loopback address.

`config/operator-recovery.json` is immutable bundle content validated before runtime startup. It
contains stable IDs, applicable fault codes, semantic action kinds, instructions, minimum roles,
and optional confirmation text. Dynamic ROS names, executables, commands, or vendor protocol data
are forbidden. Activating a bundle therefore activates an exact reviewable recovery catalog without
granting any software path around rated safety hardware.

## 6. Upgrade policy

- schema upgrades require migration tools and round-trip tests;
- adapter upgrades require contract and hardware compatibility evidence;
- ROS/Isaac upgrades occur in dedicated platform releases, not opportunistically during a cell change;
- production cells retain the previous known-good bundle.

## 7. Task 006 compiler contract

The headless compiler produces a deployment plan and canonical `manifest.json`; it does not build
native packages or containers and does not publish, install, activate, or sign a bundle. The
manifest freezes:

- source revision, cell ID, target profile, and execution mode;
- exact component type/version and instance IDs;
- the optional fixed-path approved operator recovery catalog as `config/operator-recovery.json`;
- the selected adapter package, entrypoint, and minimum version per instance;
- sorted native packages, containers, external prerequisites, recipes, and task references;
- SHA-256 and byte size for every required source/configuration file;
- the evidence-policy result.

The bundle ID is SHA-256 over compact canonical UTF-8 JSON for all manifest fields except
`bundle_id` itself. Object keys and lists with no semantic order are sorted. `manifest.json` is not
included in its own inventory. This avoids a self-reference while ensuring every frozen input hash
contributes to the content address.

Project and component references are normalized and must remain inside their allowed source root.
Task 006 checks USDA root declarations and operational prim-path uniqueness but does not claim full
OpenUSD composition validation for binary USD. Full Kit/OpenUSD scene validation remains an
engineering-stage integration check.

Production compilation cannot pass yet: the compiler deliberately emits
`compiler.production-evidence-unverified` until evidence records can be verified rather than
trusted as an unchecked caller assertion. Modeled safety connections remain metadata describing
dependencies on independent rated hardware.
