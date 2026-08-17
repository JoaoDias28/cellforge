"""Deterministic non-Kit Task 029 task and recipe authoring acceptance probe."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src" / "kit" / "cellforge.studio"))
    sys.path.insert(0, str(root / "src" / "python" / "cellforge_domain" / "src"))
    sys.path.insert(0, str(root / "src" / "python" / "cellforge_bundle" / "src"))

    from cellforge_bundle import compile_project
    from cellforge_domain import ExecutionMode

    from cellforge.studio.project_service import ProjectCommandService
    from cellforge.studio.task_service import TaskAuthoringService

    temporary_root = Path(os.environ.get("CELLFORGE_TEST_TEMP", root))
    with tempfile.TemporaryDirectory(prefix="cellforge-task029-", dir=temporary_root) as directory:
        project = Path(directory) / "pen-project"
        shutil.copytree(root / "examples" / "pen_engraving", project)
        shutil.copytree(root / "schemas", project / "schemas")
        cell_path = project / "cell.yaml"
        cell_path.write_text(
            cell_path.read_text(encoding="utf-8").replace(
                "schema: ../../schemas/recipe.schema.json", "schema: schemas/recipe.schema.json"
            ),
            encoding="utf-8",
            newline="\n",
        )

        backend = ProjectCommandService(root / "schemas")
        opened = backend.inspect(project)
        if opened.contents is None or opened.project is None:
            raise RuntimeError("Task 029 probe could not open the reference project")

        # 1. Verify task discovery and layout round trip
        tasks_browser = backend.browse_tasks(project, opened.contents)
        if not tasks_browser.tasks:
            raise RuntimeError("Task 029 probe found no tasks in project")
        task = tasks_browser.tasks[0]
        if not task.valid:
            raise RuntimeError(f"Task 029 probe found invalid starter task: {task.id}")

        # 2. Author a task with layout metadata
        task_service = TaskAuthoringService(root / "schemas")
        original_xml = (project / task.behavior_tree_path).read_text(encoding="utf-8")
        parsed_tree = task_service.parse_task_xml(original_xml)
        annotated_xml = task_service.generate_task_xml(parsed_tree, include_layout=True)

        task_edit = backend.set_task_tree(
            project,
            opened.contents,
            task_id=task.id,
            tree=annotated_xml,
        )
        if task_edit.contents is None or task_edit.validation:
            raise RuntimeError(
                f"Task 029 probe rejected annotated task edit: {task_edit.validation}"
            )

        # 3. Verify static compiler-equivalent task validation rejections
        # 3a. Unknown node
        unknown_node_xml = (
            '<root BTCPP_format="4"><BehaviorTree ID="PenEngraving">'
            "<Sequence><FakeAction/></Sequence></BehaviorTree></root>"
        )
        bad_unknown = backend.set_task_tree(
            project, task_edit.contents, task_id=task.id, tree=unknown_node_xml
        )
        if bad_unknown.contents is not None or not any(
            "unknown" in f.code for f in bad_unknown.validation
        ):
            raise RuntimeError("Task 029 probe failed to reject unknown node")

        # 3b. Process retry prohibition
        retry_proc_xml = (
            '<root BTCPP_format="4"><BehaviorTree ID="PenEngraving"><Sequence>'
            '<RetryUntilSuccessful num_attempts="3">'
            '<ExecuteProcess program="P" variable_data="{v}" recipe_id="r" recipe_version="1"/>'
            "</RetryUntilSuccessful></Sequence></BehaviorTree></root>"
        )
        bad_retry = backend.set_task_tree(
            project, task_edit.contents, task_id=task.id, tree=retry_proc_xml
        )
        if bad_retry.contents is not None or not any(
            "retry" in f.code for f in bad_retry.validation
        ):
            raise RuntimeError("Task 029 probe failed to reject process under retry")

        # 4. Recipe lifecycle: Transition to APPROVED with evidence
        recipes_browser = backend.browse_recipes(project, task_edit.contents)
        if not recipes_browser.recipes:
            raise RuntimeError("Task 029 probe found no recipes in project")

        app_transition = backend.transition_recipe_lifecycle(
            project,
            task_edit.contents,
            recipe_id="pen-aluminium-reference",
            version=1,
            target_status="APPROVED",
            evidence=["simulation:run_001_pass"],
        )
        if app_transition.contents is None:
            raise RuntimeError(
                f"Task 029 probe failed to approve recipe: {app_transition.validation}"
            )

        # 5. Verify approved recipe is immutable
        rec_detail = backend.inspect_recipe(
            project, app_transition.contents, recipe_id="pen-aluminium-reference", version=1
        )
        if rec_detail is None or not rec_detail.summary.is_immutable:
            raise RuntimeError("Task 029 probe failed to mark approved recipe as immutable")

        mutated_data = dict(rec_detail.data)
        mutated_data.setdefault("parameters", {})["robot_speed_scale"] = 0.5
        bad_edit = backend.edit_recipe(
            project,
            app_transition.contents,
            recipe_id="pen-aluminium-reference",
            version=1,
            data=mutated_data,
        )
        if bad_edit.contents is not None:
            raise RuntimeError("Task 029 probe permitted in-place mutation of approved recipe")

        # 6. Create immutable next version N+1
        v2_result = backend.create_recipe_version(
            project,
            app_transition.contents,
            recipe_id="pen-aluminium-reference",
            base_version=1,
            overrides={"parameters": {"robot_speed_scale": 0.5}},
        )
        if v2_result.contents is None:
            raise RuntimeError(f"Task 029 probe failed to create version 2: {v2_result.validation}")

        # 7. Diff recipe versions
        diff_res = backend.diff_recipes(
            project,
            v2_result.contents,
            recipe_id="pen-aluminium-reference",
            version_a=1,
            version_b=2,
        )
        if diff_res is None or not any(d.key == "robot_speed_scale" for d in diff_res.differences):
            raise RuntimeError("Task 029 probe diff did not detect parameter difference")

        # 8. Transactional save of edited task, approved v1, and draft v2
        saved = backend.save(project, v2_result.contents)
        if saved.contents is None or saved.project is None:
            raise RuntimeError(f"Task 029 probe failed to save project: {saved.validation}")

        # 9. Verify bundle compiler compiles the project with task layout annotations
        bundle_result = compile_project(
            project=project,
            schemas=project / "schemas",
            target_profile="pen-sim-amd64",
            mode=ExecutionMode.SIMULATION,
            source_revision="0" * 40,
        )
        if not bundle_result.valid:
            raise RuntimeError(f"Task 029 bundle compilation failed: {bundle_result.findings}")

    print("Verified Task 029 task and recipe authoring, lifecycle, and compilation headlessly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
