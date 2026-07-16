from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


@dataclass(frozen=True, slots=True)
class InputRecord:
    sequence: int
    path: str
    size: int
    mtime_ns: int
    selected: bool
    status: str
    output_path: str | None
    error: str | None
    newly_registered: bool = False


@dataclass(frozen=True, slots=True)
class OutputRecord:
    id: int
    path: str
    status: str
    attempts: int
    next_attempt_at: float
    last_error: str | None


class StateStore:
    """Thread-safe-by-connection SQLite state repository."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS input_files (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL UNIQUE,
                    size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    selected INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    output_path TEXT,
                    error TEXT,
                    discovered_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS output_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at REAL NOT NULL,
                    sent_at REAL
                );

                CREATE INDEX IF NOT EXISTS idx_input_status
                    ON input_files(status, selected, sequence);
                CREATE INDEX IF NOT EXISTS idx_output_queue
                    ON output_files(status, next_attempt_at, id);
                """
            )

    def register_input(self, path: Path | str, size: int, mtime_ns: int) -> InputRecord:
        normalized = _normalize_path(path)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM input_files WHERE path = ?",
                (normalized,),
            ).fetchone()
            if existing is not None:
                return _input_record(existing, newly_registered=False)

            cursor = connection.execute(
                """
                INSERT INTO input_files(path, size, mtime_ns, selected, status, discovered_at)
                VALUES (?, ?, ?, 0, 'waiting', ?)
                """,
                (normalized, int(size), int(mtime_ns), time.time()),
            )
            sequence = int(cursor.lastrowid)
            selected = (sequence - 1) % 10 == 0
            status = "waiting" if selected else "skipped"
            connection.execute(
                "UPDATE input_files SET selected = ?, status = ? WHERE sequence = ?",
                (int(selected), status, sequence),
            )
            row = connection.execute(
                "SELECT * FROM input_files WHERE sequence = ?",
                (sequence,),
            ).fetchone()
            return _input_record(row, newly_registered=True)

    def waiting_inputs(self) -> list[InputRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM input_files
                WHERE selected = 1 AND status = 'waiting'
                ORDER BY sequence
                """
            ).fetchall()
        return [_input_record(row) for row in rows]

    def mark_input_compressed(self, path: Path | str, output_path: Path | str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE input_files
                SET status = 'compressed', output_path = ?, error = NULL
                WHERE path = ?
                """,
                (_normalize_path(output_path), _normalize_path(path)),
            )

    def mark_input_failed(self, path: Path | str, error: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE input_files SET status = 'failed', error = ? WHERE path = ?",
                (error[:2000], _normalize_path(path)),
            )

    def register_output(self, path: Path | str) -> OutputRecord:
        normalized = _normalize_path(path)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO output_files(path, status, attempts, next_attempt_at, created_at)
                VALUES (?, 'pending', 0, 0, ?)
                """,
                (normalized, time.time()),
            )
            row = connection.execute(
                "SELECT * FROM output_files WHERE path = ?",
                (normalized,),
            ).fetchone()
        return _output_record(row)

    def next_pending_output(self, *, now: float | None = None) -> OutputRecord | None:
        current_time = time.time() if now is None else now
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM output_files
                WHERE status IN ('pending', 'retry')
                ORDER BY id
                LIMIT 1
                """
            ).fetchone()
        if row is not None and float(row["next_attempt_at"]) > current_time:
            return None
        return _output_record(row) if row is not None else None

    def mark_output_sent(self, output_id: int, *, sent_at: float | None = None) -> None:
        timestamp = time.time() if sent_at is None else sent_at
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE output_files
                SET status = 'sent', sent_at = ?, last_error = NULL
                WHERE id = ?
                """,
                (timestamp, output_id),
            )

    def mark_output_retry(self, output_id: int, error: str, *, next_attempt_at: float) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE output_files
                SET status = 'retry', attempts = attempts + 1,
                    next_attempt_at = ?, last_error = ?
                WHERE id = ?
                """,
                (next_attempt_at, error[:2000], output_id),
            )

    def mark_output_failed(self, output_id: int, error: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE output_files
                SET status = 'failed', last_error = ?
                WHERE id = ?
                """,
                (error[:2000], output_id),
            )

    def reset_all(self) -> None:
        """清空全部处理和发送记录，并让文件序号重新从 1 开始。"""

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM output_files")
            connection.execute("DELETE FROM input_files")
            connection.execute(
                """
                DELETE FROM sqlite_sequence
                WHERE name IN ('input_files', 'output_files')
                """
            )
            
    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            discovered = _scalar(connection, "SELECT COUNT(*) FROM input_files")
            compressed = _scalar(connection, "SELECT COUNT(*) FROM input_files WHERE status = 'compressed'")
            failed = _scalar(connection, "SELECT COUNT(*) FROM input_files WHERE status = 'failed'")
            pending_send = _scalar(
                connection,
                "SELECT COUNT(*) FROM output_files WHERE status IN ('pending', 'retry')",
            )
            sent = _scalar(connection, "SELECT COUNT(*) FROM output_files WHERE status = 'sent'")
            failed_send = _scalar(connection, "SELECT COUNT(*) FROM output_files WHERE status = 'failed'")
        return {
            "discovered": discovered,
            "compressed": compressed,
            "failed": failed,
            "pending_send": pending_send,
            "sent": sent,
            "failed_send": failed_send,
        }


def _normalize_path(path: Path | str) -> str:
    return os.path.normcase(str(Path(path).expanduser().resolve(strict=False)))


def _input_record(row: sqlite3.Row, *, newly_registered: bool = False) -> InputRecord:
    return InputRecord(
        sequence=int(row["sequence"]),
        path=str(row["path"]),
        size=int(row["size"]),
        mtime_ns=int(row["mtime_ns"]),
        selected=bool(row["selected"]),
        status=str(row["status"]),
        output_path=row["output_path"],
        error=row["error"],
        newly_registered=newly_registered,
    )


def _output_record(row: sqlite3.Row) -> OutputRecord:
    return OutputRecord(
        id=int(row["id"]),
        path=str(row["path"]),
        status=str(row["status"]),
        attempts=int(row["attempts"]),
        next_attempt_at=float(row["next_attempt_at"]),
        last_error=row["last_error"],
    )


def _scalar(connection: sqlite3.Connection, query: str) -> int:
    row: Any = connection.execute(query).fetchone()
    return int(row[0])
