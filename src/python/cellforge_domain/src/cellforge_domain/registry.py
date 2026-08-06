"""Deterministic filesystem discovery for versioned component packages."""

from dataclasses import dataclass
from pathlib import Path

from cellforge_domain.base import DomainModel
from cellforge_domain.findings import FindingSeverity, SourceLoadError, ValidationFinding
from cellforge_domain.identifiers import ComponentTypeIdentifier, SemanticVersion
from cellforge_domain.loading import load_document
from cellforge_domain.models import ComponentType
from cellforge_domain.schemas import SchemaRegistry


class RegistryComponent(DomainModel):
    """Serializable identity and source location for one registered package."""

    component: ComponentTypeIdentifier
    version: SemanticVersion
    package_path: str


@dataclass(frozen=True, slots=True)
class RegisteredComponentPackage:
    """A loaded manifest plus its deterministic registry-relative source path."""

    manifest: ComponentType
    source_path: Path
    package_path: str


class FilesystemComponentRegistry:
    """An exact-version component index loaded from a caller-owned filesystem root."""

    def __init__(
        self,
        *,
        root: Path,
        packages: dict[tuple[str, str], RegisteredComponentPackage],
        findings: tuple[ValidationFinding, ...],
    ) -> None:
        self.root = root
        self._packages = dict(packages)
        self.findings = findings

    @classmethod
    def from_directory(
        cls,
        root: str | Path,
        *,
        schema_registry: SchemaRegistry | None = None,
    ) -> "FilesystemComponentRegistry":
        """Discover every ``component.yaml`` below ``root`` in sorted path order.

        Invalid or duplicate manifests are retained as findings and excluded from exact lookup.
        Multiple distinct semantic versions of one component type are valid registry entries.
        """

        root_path = Path(root).resolve()
        if not root_path.is_dir():
            return cls(
                root=root_path,
                packages={},
                findings=(
                    ValidationFinding(
                        code="registry.root-not-found",
                        severity=FindingSeverity.ERROR,
                        path=f"{root_path}#",
                        message="Component registry root is not a readable directory.",
                    ),
                ),
            )

        try:
            manifests = sorted(
                root_path.rglob("component.yaml"),
                key=lambda path: path.relative_to(root_path).as_posix(),
            )
        except OSError:
            return cls(
                root=root_path,
                packages={},
                findings=(
                    ValidationFinding(
                        code="registry.scan-failed",
                        severity=FindingSeverity.ERROR,
                        path=f"{root_path}#",
                        message="Component registry could not be scanned.",
                    ),
                ),
            )

        if not manifests:
            return cls(
                root=root_path,
                packages={},
                findings=(
                    ValidationFinding(
                        code="registry.no-component-manifests",
                        severity=FindingSeverity.ERROR,
                        path=f"{root_path}#",
                        message="Component registry contains no component.yaml manifests.",
                    ),
                ),
            )

        packages: dict[tuple[str, str], RegisteredComponentPackage] = {}
        findings: list[ValidationFinding] = []
        for source_path in manifests:
            package_path = source_path.parent.relative_to(root_path).as_posix()
            try:
                manifest = load_document(
                    source_path,
                    ComponentType,
                    schema_registry=schema_registry,
                )
            except SourceLoadError as error:
                findings.append(
                    ValidationFinding(
                        code="registry.manifest-invalid",
                        severity=FindingSeverity.ERROR,
                        path=f"{package_path}/component.yaml#",
                        message=f"Component manifest is invalid ({error.code}).",
                    )
                )
                continue

            key = (manifest.component.id, manifest.component.version)
            existing = packages.get(key)
            if existing is not None:
                findings.append(
                    ValidationFinding(
                        code="registry.duplicate-component-version",
                        severity=FindingSeverity.ERROR,
                        path=f"{package_path}/component.yaml#/component/version",
                        message=(
                            f"Component '{key[0]}' version '{key[1]}' is already registered at "
                            f"'{existing.package_path}/component.yaml'."
                        ),
                    )
                )
                continue

            packages[key] = RegisteredComponentPackage(
                manifest=manifest,
                source_path=source_path,
                package_path=package_path,
            )

        return cls(
            root=root_path,
            packages=packages,
            findings=tuple(sorted(findings, key=_finding_sort_key)),
        )

    @property
    def components(self) -> tuple[RegistryComponent, ...]:
        """Return the deterministic serializable registry inventory."""

        return tuple(
            RegistryComponent(
                component=package.manifest.component.id,
                version=package.manifest.component.version,
                package_path=package.package_path,
            )
            for package in sorted(
                self._packages.values(),
                key=lambda item: (
                    item.manifest.component.id,
                    item.manifest.component.version,
                    item.package_path,
                ),
            )
        )

    def get(
        self,
        component: ComponentTypeIdentifier,
        version: SemanticVersion,
    ) -> RegisteredComponentPackage | None:
        """Return one exact package match without applying fallback version selection."""

        return self._packages.get((component, version))

    def versions(self, component: ComponentTypeIdentifier) -> tuple[str, ...]:
        """Return all registered versions for one component type in deterministic order."""

        return tuple(
            sorted(version for candidate, version in self._packages if candidate == component)
        )


def _finding_sort_key(finding: ValidationFinding) -> tuple[str, str, str]:
    return finding.path, finding.code, finding.message
