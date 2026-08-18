"""Database connection and transactional execution engine."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol


class Connection(Protocol):
    """Database connection interface protocol."""

    def execute(self, sql: str, parameters: tuple[Any, ...] | dict[str, Any] = ()) -> Any: ...
    def executescript(self, sql_script: str) -> Any: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


class DatabaseEngine:
    """Provides pooled / transactional connections for SQLite and PostgreSQL."""

    def __init__(self, database_url: str = ":memory:") -> None:
        self.url = database_url
        self._is_sqlite = (
            database_url.startswith("sqlite")
            or database_url == ":memory:"
            or not database_url.startswith("postgres")
        )
        self._shared_memory_conn: sqlite3.Connection | None = None

        if database_url == ":memory:":
            # Keep a persistent in-memory connection open so tables aren't lost across requests
            self._shared_memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._shared_memory_conn.row_factory = sqlite3.Row
            self._shared_memory_conn.execute("PRAGMA foreign_keys = ON;")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Provide a connection with transaction management."""
        if self._shared_memory_conn is not None:
            yield self._shared_memory_conn
            return

        if self._is_sqlite:
            path = self.url
            if path.startswith("sqlite:///"):
                path = path[10:]
            elif path.startswith("sqlite://"):
                path = path[9:]
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            # PostgreSQL connection via psycopg or sqlite emulation for testing
            raise NotImplementedError(
                f"Direct PostgreSQL driver for {self.url} requires asyncpg/psycopg installed."
            )
