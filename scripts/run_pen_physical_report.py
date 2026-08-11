"""Generate reproducible Task 020 seeded-cycle evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--first-seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "ros_ws" / "src" / "cellforge_simulation"))
    from cellforge_simulation.physical import build_seed_report, write_seed_report

    report = build_seed_report(arguments.seeds, first_seed=arguments.first_seed)
    write_seed_report(arguments.output, report)
    payload = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    print(
        f"Task 020 report: {report['summary']['passed']}/{arguments.seeds} passed; "
        f"canonical_sha256={hashlib.sha256(payload).hexdigest()}"
    )
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
