"""Locate canonical CLI resources in source checkouts and installed wheels."""

from dataclasses import dataclass
from pathlib import Path


class ResourceUnavailableError(Exception):
    """Safe failure raised when required packaged engineering resources are absent."""


@dataclass(frozen=True, slots=True)
class CliResources:
    """Physical paths to the schemas and canonical pen project used by CLI commands."""

    schema_directory: Path
    pen_example_directory: Path

    @classmethod
    def discover(cls) -> "CliResources":
        """Find packaged resources first, then the canonical source-checkout directories."""

        package_directory = Path(__file__).resolve().parent
        packaged_root = package_directory / "resources"
        packaged = cls(
            schema_directory=packaged_root / "schemas",
            pen_example_directory=packaged_root / "examples" / "pen_engraving",
        )
        if packaged.is_available:
            return packaged

        for candidate in package_directory.parents:
            source = cls(
                schema_directory=candidate / "schemas",
                pen_example_directory=candidate / "examples" / "pen_engraving",
            )
            if source.is_available:
                return source

        raise ResourceUnavailableError(
            "Canonical schemas and the pen-engraving example are unavailable."
        )

    @property
    def is_available(self) -> bool:
        """Return whether both required resource trees have their canonical entry files."""

        return (self.schema_directory / "cell.schema.json").is_file() and (
            self.pen_example_directory / "cell.yaml"
        ).is_file()
