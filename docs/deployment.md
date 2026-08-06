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
│   └── target profile
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

## 5. Secrets

Secrets are never stored in cell source, recipes, or bundles. Target installation resolves secret references from local protected storage.

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
