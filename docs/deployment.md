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
