"""The ResultStore class saves completed Agent 2 research results into a SQLite database while attempting to exclude private
 execution state."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from shared import ServiceError

DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "assistant.sqlite3"
TERMINAL_STATUSES = {"complete", "partial", "empty", "failed"}

class ResultStore:
    def __init__(self, path=DATABASE_PATH):
        self.path = Path(path)

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True) 
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.execute("""
            CREATE TABLE IF NOT EXISTS agent2_results (
                task_id TEXT PRIMARY KEY,
                saved_at TEXT NOT NULL,
                snapshot_json TEXT NOT NULL
            )""")
        except Exception:
            connection.close()
            raise
        return connection

    # this function will save the data inside SQLite database.
    def save(self, snapshot):
        if snapshot.get("status") not in TERMINAL_STATUSES or not isinstance(snapshot.get("result"), dict):
            raise ServiceError("Only finished research runs can be saved.", 409, code="not_finished")
        public = {key: snapshot[key] for key in ("task_id", "status", "request", "events", "result")}
        encoded = json.dumps(public, ensure_ascii=False, allow_nan=False)
        saved_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            connection = self._connect()
            try:
                with connection:
                    connection.execute(
                        "INSERT OR IGNORE INTO agent2_results (task_id, saved_at, snapshot_json) VALUES (?, ?, ?)",
                        (public["task_id"], saved_at, encoded))
                    saved_at = connection.execute(
                        "SELECT saved_at FROM agent2_results WHERE task_id = ?", (public["task_id"],)).fetchone()[0]
            finally:
                connection.close() 
        except (OSError, sqlite3.Error):
            raise ServiceError("Could not save the result to SQLite. The research result is still available; retry saving.",
                               503, code="storage_error") from None
        return {"status": "saved", "saved_at": saved_at, "database_path": str(self.path)}

    def load_task(self, task_id):
        """Read one public snapshot for Agent 3 without loading all saved runs."""
        try:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT snapshot_json FROM agent2_results WHERE task_id = ?", (task_id,)).fetchone()
            finally:
                connection.close()
            snapshot = json.loads(row[0]) if row else None
        except (OSError, sqlite3.Error, ValueError):
            raise ServiceError("Could not read the saved research result from SQLite.",
                               503, code="storage_error") from None
        if snapshot is None:
            raise ServiceError("This research run was not found in memory or SQLite.",
                               404, code="task_not_found")
        return snapshot

    # this will retrieve the result from SQLite file.
    def load_all(self):
        try:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT saved_at, snapshot_json FROM agent2_results ORDER BY saved_at DESC, task_id").fetchall()
            finally:
                connection.close()
            results = [{"saved_at": saved_at, "snapshot": json.loads(encoded)} for saved_at, encoded in rows]
        except (OSError, sqlite3.Error, ValueError):
            raise ServiceError("Could not read saved results from SQLite.", 503, code="storage_error") from None
        return {"database_path": str(self.path), "count": len(results), "results": results}


RESULT_STORE = ResultStore()



