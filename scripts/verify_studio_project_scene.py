"""Deterministic Task 015 acceptance probe without Kit, a GPU, or project writes."""

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src" / "kit" / "cellforge.studio"))
    from cellforge.studio.backend import create_default_application

    project = root / "examples" / "pen_engraving"
    canonical = (project / "cell.yaml", project / "scene.usda")
    before = tuple(path.read_bytes() for path in canonical)
    application = create_default_application()
    snapshot = application.open_project(project)
    after = tuple(path.read_bytes() for path in canonical)
    if snapshot.project is None or snapshot.validation:
        print("Pen project did not open with synchronized canonical sources.", file=sys.stderr)
        return 1
    if snapshot.project.component_count != 6 or snapshot.dirty:
        print("Pen project summary or dirty state is incorrect.", file=sys.stderr)
        return 1
    if before != after:
        print("Opening the pen project modified canonical project files.", file=sys.stderr)
        return 1
    print("Verified Task 015 pen project/scene open and synchronized instance IDs read-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
