from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
from typing import Any


class ReportStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    intelligence_json TEXT NOT NULL,
                    report_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS macro_cache (
                    series TEXT PRIMARY KEY,
                    cached_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def save(self, intelligence: dict[str, Any], report: dict[str, Any]) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO reports (asset, timeframe, generated_at, intelligence_json, report_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    report["asset"],
                    report["timeframe"],
                    report["generated_at"],
                    json.dumps(intelligence, ensure_ascii=False),
                    json.dumps(report, ensure_ascii=False),
                ),
            )
            connection.commit()

    def latest(self) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT intelligence_json, report_json
                FROM reports
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        if row is None:
            return None
        return {
            "intelligence": json.loads(row["intelligence_json"]),
            "report": json.loads(row["report_json"]),
        }

    def save_macro_cache(
        self,
        *,
        series: str,
        cached_at: str,
        payload: dict[str, Any],
    ) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO macro_cache (series, cached_at, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(series) DO UPDATE SET
                    cached_at = excluded.cached_at,
                    payload_json = excluded.payload_json
                """,
                (
                    series,
                    cached_at,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            connection.commit()

    def load_macro_cache(self, series: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT series, cached_at, payload_json
                FROM macro_cache
                WHERE series = ?
                LIMIT 1
                """,
                (series,),
            ).fetchone()

        if row is None:
            return None
        return {
            "series": row["series"],
            "cached_at": row["cached_at"],
            "payload": json.loads(row["payload_json"]),
        }
