"""Platform server CLI entrypoint."""

from __future__ import annotations

import argparse
import sys

import uvicorn

from cellforge_platform.api.router import create_platform_app
from cellforge_platform.config import PlatformSettings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CellForge Platform Service")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument(
        "--env", default="development", choices=["development", "staging", "production"]
    )
    parser.add_argument("--db", default=":memory:", help="Database connection URL")
    parser.add_argument(
        "--storage-root", default="var/platform_artifacts", help="Artifact store directory"
    )

    args = parser.parse_args(argv or sys.argv[1:])
    settings = PlatformSettings.from_env(
        environment=args.env,
        database_url=args.db,
        storage_root=args.storage_root,
    )
    app = create_platform_app(settings)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
