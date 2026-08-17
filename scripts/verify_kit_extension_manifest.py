"""Verify Task 014 extension discovery metadata without requiring Isaac Sim."""

import sys
import tomllib
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    extension = root / "src" / "kit" / "cellforge.studio"
    manifest_path = extension / "config" / "extension.toml"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    modules = manifest.get("python", {}).get("module", [])
    if modules != [{"name": "cellforge.studio.extension"}]:
        print("Invalid Cell Studio Python module declaration.", file=sys.stderr)
        return 1
    for relative in (
        "cellforge/studio/__init__.py",
        "cellforge/studio/application.py",
        "cellforge/studio/backend.py",
        "cellforge/studio/component_service.py",
        "cellforge/studio/connection_service.py",
        "cellforge/studio/deployment_service.py",
        "cellforge/studio/extension.py",
        "cellforge/studio/project_service.py",
        "cellforge/studio/recipe_service.py",
        "cellforge/studio/scenario_service.py",
        "cellforge/studio/scene.py",
        "cellforge/studio/simulation_application.py",
        "cellforge/studio/simulation_backend.py",
        "cellforge/studio/simulation_host.py",
        "cellforge/studio/spatial_configuration.py",
        "cellforge/studio/task_service.py",
    ):
        if not (extension / relative).is_file():
            print(f"Missing extension source: {relative}", file=sys.stderr)
            return 1
    print("Verified cellforge.studio extension metadata and source layout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
