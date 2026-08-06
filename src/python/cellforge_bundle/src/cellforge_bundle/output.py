"""Immutable compiler-output materialization."""

from pathlib import Path


class ManifestWriteError(Exception):
    """Sanitized manifest output failure."""

    def __init__(self, output_path: Path, message: str) -> None:
        self.output_path = output_path
        self.message = message
        super().__init__(f"{output_path}: {message}")


def write_manifest(output: str | Path, manifest_json: str) -> Path:
    """Create a manifest exactly once; immutable output is never overwritten."""

    output_path = Path(output).resolve()
    try:
        with output_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(manifest_json)
            stream.write("\n")
    except FileExistsError:
        raise ManifestWriteError(output_path, "Manifest output already exists.") from None
    except OSError:
        raise ManifestWriteError(output_path, "Could not create manifest output.") from None
    return output_path
