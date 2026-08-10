"""Typed command-line entry point for CellForge engineering workflows."""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from cellforge_bundle import ManifestWriteError, compile_project, write_manifest
from cellforge_domain import (
    ExecutionMode,
    FindingSeverity,
    SchemaRegistry,
    SchemaRegistryError,
    ValidationFinding,
)
from cellforge_domain.example_validation import format_finding

from cellforge_cli.exit_codes import ExitCode
from cellforge_cli.projects import (
    ProjectOperationError,
    copy_example,
    initialize_project,
    inspect_project,
    resolve_project_schema_directory,
    validate_project,
)
from cellforge_cli.resources import CliResources, ResourceUnavailableError


@dataclass(frozen=True, slots=True)
class CommandResult:
    """One rendered CLI result with a stable process status and structured findings."""

    command: str
    exit_code: ExitCode
    message: str
    data: dict[str, object]
    findings: tuple[ValidationFinding, ...] = ()

    @property
    def ok(self) -> bool:
        return self.exit_code is ExitCode.SUCCESS

    def payload(self) -> dict[str, object]:
        """Build the stable JSON output envelope."""

        return {
            "command": self.command,
            "errors": [finding.model_dump(mode="json") for finding in self.findings],
            "exit_code": int(self.exit_code),
            "message": self.message,
            "ok": self.ok,
            "result": self.data,
        }


def build_parser() -> argparse.ArgumentParser:
    """Build the public command tree without importing optional platform software."""

    parser = argparse.ArgumentParser(prog="cellforge", description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit one deterministic JSON result envelope (accepted anywhere in a command)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    project = commands.add_parser("project", help="create and manage project scaffolds")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    project_init = project_commands.add_parser("init", help="create a simulation-only starter")
    project_init.add_argument("path", type=Path)

    validate = commands.add_parser("validate", help="validate a project tree")
    validate.add_argument("project", type=Path)

    inspect = commands.add_parser("inspect", help="summarize a valid project")
    inspect.add_argument("project", type=Path)

    build = commands.add_parser("build", help="compile a deterministic bundle manifest")
    build.add_argument("project", type=Path)
    build.add_argument("--target", required=True, help="exact target profile ID")
    build.add_argument(
        "--mode",
        required=True,
        choices=tuple(mode.value for mode in ExecutionMode),
        help="execution mode to resolve",
    )
    build.add_argument(
        "--source-revision",
        required=True,
        help="exact lowercase 40-character Git commit hash",
    )
    build.add_argument("--output", type=Path, help="create manifest JSON without overwriting")

    schema = commands.add_parser("schema", help="work with canonical schemas")
    schema_commands = schema.add_subparsers(dest="schema_command", required=True)
    schema_commands.add_parser("list", help="list schema kinds and versions")

    example = commands.add_parser("example", help="work with canonical examples")
    example_commands = example.add_subparsers(dest="example_command", required=True)
    example_copy = example_commands.add_parser("copy", help="copy a canonical example")
    example_copy.add_argument("name", choices=("pen-engraving",))
    example_copy.add_argument("path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and return a stable integer exit code."""

    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    json_output = "--json" in raw_arguments
    arguments = [argument for argument in raw_arguments if argument != "--json"]
    namespace = build_parser().parse_args(arguments)

    result = _dispatch(namespace)
    _render(result, json_output=json_output)
    return int(result.exit_code)


def _dispatch(arguments: argparse.Namespace) -> CommandResult:
    command = str(arguments.command)
    if command == "project":
        return _project_init(Path(arguments.path))

    resources_result = _resources(command)
    if isinstance(resources_result, CommandResult):
        return resources_result
    resources = resources_result

    try:
        schema_directory: Path | CommandResult = resources.schema_directory
        if command in {"validate", "inspect", "build"}:
            schema_directory = _verified_project_schemas(
                command, Path(arguments.project), resources.schema_directory
            )
        if isinstance(schema_directory, CommandResult):
            return schema_directory

        registry = SchemaRegistry.from_directory(schema_directory)
    except SchemaRegistryError as error:
        return _failure(
            command=command,
            exit_code=ExitCode.RESOURCE_UNAVAILABLE,
            code="cli.schema-registry-unavailable",
            path=error.source_path,
            message=error.message,
        )

    if command == "validate":
        return _validate(Path(arguments.project), registry)
    if command == "inspect":
        return _inspect(Path(arguments.project), registry)
    if command == "build":
        return _build(
            Path(arguments.project),
            schema_directory,
            target=str(arguments.target),
            mode=ExecutionMode(str(arguments.mode)),
            source_revision=str(arguments.source_revision),
            output=Path(arguments.output) if arguments.output is not None else None,
        )
    if command == "schema":
        return _schema_list(registry)
    if command == "example":
        return _example_copy(resources, Path(arguments.path))
    return _failure(
        command=command,
        exit_code=ExitCode.USAGE_ERROR,
        code="cli.unknown-command",
        path=Path.cwd(),
        message="Unknown command.",
    )


def _project_init(destination: Path) -> CommandResult:
    try:
        cell_id = initialize_project(destination)
    except ProjectOperationError as error:
        return CommandResult(
            command="project.init",
            exit_code=error.exit_code,
            message=error.finding.message,
            data={"path": str(destination.resolve())},
            findings=(error.finding,),
        )
    project_path = destination.resolve()
    return CommandResult(
        command="project.init",
        exit_code=ExitCode.SUCCESS,
        message=f"Initialized simulation-only project at {project_path}.",
        data={"cell_id": str(cell_id), "path": str(project_path)},
    )


def _validate(project: Path, registry: SchemaRegistry) -> CommandResult:
    report = validate_project(project, registry)
    project_path = project.resolve()
    data: dict[str, object] = {
        "auxiliary_schemas_checked": report.auxiliary_schemas_checked,
        "documents_checked": report.documents_checked,
        "path": str(project_path),
        "schemas_checked": len(registry),
    }
    if report.findings:
        exit_code = (
            ExitCode.INPUT_NOT_FOUND
            if report.findings[0].code == "cli.project-not-found"
            else ExitCode.VALIDATION_FAILED
        )
        return CommandResult(
            command="validate",
            exit_code=exit_code,
            message=f"Project validation failed with {len(report.findings)} error(s).",
            data=data,
            findings=report.findings,
        )
    return CommandResult(
        command="validate",
        exit_code=ExitCode.SUCCESS,
        message=(
            f"Valid project {project_path}: {report.documents_checked} document(s), "
            f"{report.auxiliary_schemas_checked} component schema(s)."
        ),
        data=data,
    )


def _inspect(project: Path, registry: SchemaRegistry) -> CommandResult:
    validation = validate_project(project, registry)
    if validation.findings:
        exit_code = (
            ExitCode.INPUT_NOT_FOUND
            if validation.findings[0].code == "cli.project-not-found"
            else ExitCode.VALIDATION_FAILED
        )
        return CommandResult(
            command="inspect",
            exit_code=exit_code,
            message=(
                f"Project inspection blocked by {len(validation.findings)} validation error(s)."
            ),
            data={"path": str(project.resolve())},
            findings=validation.findings,
        )
    try:
        summary = inspect_project(project, registry)
    except ProjectOperationError as error:
        return CommandResult(
            command="inspect",
            exit_code=error.exit_code,
            message=error.finding.message,
            data={"path": str(project.resolve())},
            findings=(error.finding,),
        )
    return CommandResult(
        command="inspect",
        exit_code=ExitCode.SUCCESS,
        message=f"CellForge project: {summary.name} ({summary.cell_id})",
        data=summary.as_dict(),
    )


def _build(
    project: Path,
    schemas: Path,
    *,
    target: str,
    mode: ExecutionMode,
    source_revision: str,
    output: Path | None,
) -> CommandResult:
    report = compile_project(
        project,
        schemas,
        target_profile=target,
        mode=mode,
        source_revision=source_revision,
    )
    data: dict[str, object] = {
        "execution_mode": mode.value,
        "path": str(project.resolve()),
        "stages": [stage.model_dump(mode="json") for stage in report.stages],
        "target_profile": target,
    }
    if not report.valid or report.manifest is None or report.manifest_json is None:
        exit_code = (
            ExitCode.INPUT_NOT_FOUND
            if any(finding.code == "compiler.project-not-found" for finding in report.findings)
            else ExitCode.VALIDATION_FAILED
        )
        return CommandResult(
            command="build",
            exit_code=exit_code,
            message=f"Bundle compilation failed with {len(report.findings)} finding(s).",
            data=data,
            findings=report.findings,
        )

    data["bundle_id"] = report.manifest.bundle_id
    data["manifest"] = report.manifest.model_dump(mode="json", by_alias=True)
    if output is not None:
        try:
            written = write_manifest(output, report.manifest_json)
        except ManifestWriteError as error:
            finding = ValidationFinding(
                code="cli.manifest-write-failed",
                severity=FindingSeverity.ERROR,
                path=f"{error.output_path}#",
                message=error.message,
            )
            return CommandResult(
                command="build",
                exit_code=ExitCode.OPERATION_FAILED,
                message=error.message,
                data=data,
                findings=(finding,),
            )
        data["output"] = str(written)
    return CommandResult(
        command="build",
        exit_code=ExitCode.SUCCESS,
        message=f"Compiled immutable manifest {report.manifest.bundle_id}.",
        data=data,
    )


def _schema_list(registry: SchemaRegistry) -> CommandResult:
    schemas: list[dict[str, object]] = []
    for key in registry.keys:
        registered = registry.get(key.kind, key.version)
        schemas.append(
            {
                "filename": registered.path.name,
                "id": registered.identifier,
                "kind": key.kind.value,
                "version": key.version,
            }
        )
    return CommandResult(
        command="schema.list",
        exit_code=ExitCode.SUCCESS,
        message=f"{len(schemas)} canonical schema(s) registered.",
        data={"schemas": schemas},
    )


def _example_copy(resources: CliResources, destination: Path) -> CommandResult:
    try:
        copy_example(
            resources.pen_example_directory,
            resources.schema_directory,
            destination,
        )
    except ProjectOperationError as error:
        return CommandResult(
            command="example.copy",
            exit_code=error.exit_code,
            message=error.finding.message,
            data={"example": "pen-engraving", "path": str(destination.resolve())},
            findings=(error.finding,),
        )
    destination_path = destination.resolve()
    return CommandResult(
        command="example.copy",
        exit_code=ExitCode.SUCCESS,
        message=f"Copied pen-engraving example to {destination_path}.",
        data={"example": "pen-engraving", "path": str(destination_path)},
    )


def _verified_project_schemas(
    command: str,
    project: Path,
    canonical_schemas: Path,
) -> Path | CommandResult:
    """Use portable project schemas only when they exactly match the canonical set."""
    try:
        return resolve_project_schema_directory(project, canonical_schemas)
    except ProjectOperationError as error:
        return CommandResult(
            command=command,
            exit_code=error.exit_code,
            message=error.finding.message,
            data={},
            findings=(error.finding,),
        )


def _resources(command: str) -> CliResources | CommandResult:
    try:
        return CliResources.discover()
    except ResourceUnavailableError as error:
        return _failure(
            command=command,
            exit_code=ExitCode.RESOURCE_UNAVAILABLE,
            code="cli.resources-unavailable",
            path=Path.cwd(),
            message=str(error),
        )


def _failure(
    *,
    command: str,
    exit_code: ExitCode,
    code: str,
    path: Path,
    message: str,
) -> CommandResult:
    finding = ValidationFinding(
        code=code,
        severity=FindingSeverity.ERROR,
        path=f"{path.resolve()}#",
        message=message,
    )
    return CommandResult(
        command=command,
        exit_code=exit_code,
        message=message,
        data={},
        findings=(finding,),
    )


def _render(result: CommandResult, *, json_output: bool) -> None:
    if json_output:
        print(
            json.dumps(result.payload(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        )
        return
    stream = sys.stdout if result.ok else sys.stderr
    print(result.message, file=stream)
    if result.ok and result.command == "schema.list":
        schemas = result.data["schemas"]
        if isinstance(schemas, list):
            for schema in schemas:
                if isinstance(schema, dict):
                    print(
                        f"{schema['kind']} {schema['version']} {schema['id']} "
                        f"({schema['filename']})",
                        file=stream,
                    )
    elif result.ok and result.command == "build":
        print(f"bundle_id: {result.data['bundle_id']}", file=stream)
        if "output" in result.data:
            print(f"output: {result.data['output']}", file=stream)
    elif result.ok and result.command == "inspect":
        for key in (
            "path",
            "scene",
            "component_count",
            "connection_count",
            "task_count",
            "recipe_count",
            "scenario_count",
            "deployment_profile_count",
        ):
            print(f"{key}: {result.data[key]}", file=stream)
    elif not result.ok:
        for finding in result.findings:
            print(format_finding(finding), file=stream)


if __name__ == "__main__":
    raise SystemExit(main())
