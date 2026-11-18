"""SQLite conversations and immutable graph snapshots, isolated by numeric chat ID."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from shared import ServiceError
from shared.result_store import DATABASE_PATH


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


class ChatStore:
    def __init__(self, path=DATABASE_PATH):
        self.path = Path(path)

    @contextmanager
    def database(self):
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS assistant_chats (
                    chat_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assistant_turns (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id TEXT NOT NULL UNIQUE,
                    chat_id INTEGER NOT NULL REFERENCES assistant_chats(chat_id),
                    message TEXT NOT NULL,
                    status TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS assistant_turns_by_chat
                    ON assistant_turns(chat_id, sequence);
                CREATE TABLE IF NOT EXISTS assistant_chat_results (
                    graph_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL REFERENCES assistant_chats(chat_id),
                    reference_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    UNIQUE(chat_id, reference_json)
                );
                CREATE TABLE IF NOT EXISTS overview_results (
                    result_id TEXT PRIMARY KEY,
                    snapshot_json TEXT NOT NULL
                );
            """)
            with connection:
                yield connection
        except (OSError, sqlite3.Error, ValueError):
            raise ServiceError("Could not read or save the conversation in SQLite. Please try again.",
                               503, code="storage_error") from None
        finally:
            if connection is not None:
                connection.close()

    def require_chat(self, connection, chat_id):
        if type(chat_id) is not int or chat_id < 1:
            raise ServiceError("Select a saved conversation.", 400, code="invalid_chat")
        row = connection.execute("SELECT * FROM assistant_chats WHERE chat_id = ?", (chat_id,)).fetchone()
        if row is None:
            raise ServiceError("This conversation was not found.", 404, code="chat_not_found")
        return dict(row)

    def create_chat(self):
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        with self.database() as connection:
            cursor = connection.execute(
                "INSERT INTO assistant_chats (title, created_at, updated_at) VALUES (?, ?, ?)",
                ("New conversation", now, now))
            return self.require_chat(connection, cursor.lastrowid)

    def list_chats(self):
        with self.database() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM assistant_chats ORDER BY updated_at DESC, chat_id DESC")]

    def load_chat(self, chat_id):
        with self.database() as connection:
            chat = self.require_chat(connection, chat_id)
            chat["turns"] = [json.loads(row[0]) for row in connection.execute(
                "SELECT snapshot_json FROM assistant_turns WHERE chat_id = ? ORDER BY sequence", (chat_id,))]
            chat["graphs"] = [
                {"graph_id": row["graph_id"], "reference": json.loads(row["reference_json"]),
                 "result": json.loads(row["result_json"])}
                for row in connection.execute(
                    "SELECT * FROM assistant_chat_results WHERE chat_id = ? ORDER BY graph_id", (chat_id,))]
            return chat

    def start_turn(self, chat_id, turn_id, message, *, provider="auto"):
        """Reserve one active turn per chat and make repeated submissions idempotent."""
        with self.database() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self.require_chat(connection, chat_id)
            existing = connection.execute(
                "SELECT chat_id, message, snapshot_json FROM assistant_turns WHERE turn_id = ?", (turn_id,)).fetchone()
            if existing:
                if (existing["chat_id"] != chat_id or existing["message"] != message
                        or json.loads(existing["snapshot_json"]).get("provider", "auto") != provider):
                    raise ServiceError("This message reference is already in use.", 409)
                return json.loads(existing["snapshot_json"]), False
            active = connection.execute(
                "SELECT 1 FROM assistant_turns WHERE chat_id = ? AND status IN ('running', 'needs_clarification')",
                (chat_id,)).fetchone()
            if active:
                raise ServiceError("Finish the current request in this chat first.", 409, code="chat_busy")
            snapshot = {"id": turn_id, "turn_id": turn_id, "chat_id": chat_id, "message": message,
                        "status": "running", "text": "", "outputs": [], "events": [], "choices": {},
                        "provider": provider}
            connection.execute(
                "INSERT INTO assistant_turns (turn_id, chat_id, message, status, snapshot_json) VALUES (?, ?, ?, ?, ?)",
                (turn_id, chat_id, message, "running", encode(snapshot)))
            now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            connection.execute(
                "UPDATE assistant_chats SET title = CASE WHEN title = 'New conversation' THEN ? ELSE title END, "
                "updated_at = ? WHERE chat_id = ?", (message[:80], now, chat_id))
            return snapshot, True

    def save_turn(self, chat_id, snapshot):
        with self.database() as connection:
            cursor = connection.execute(
                "UPDATE assistant_turns SET status = ?, snapshot_json = ? WHERE chat_id = ? AND turn_id = ?",
                (snapshot["status"], encode(snapshot), chat_id, snapshot["turn_id"]))
            if cursor.rowcount != 1:
                raise ServiceError("This request does not belong to this chat.", 404)
            connection.execute("UPDATE assistant_chats SET updated_at = ? WHERE chat_id = ?",
                               (datetime.now(timezone.utc).isoformat(timespec="microseconds"), chat_id))

    def load_turn(self, chat_id, turn_id):
        with self.database() as connection:
            row = connection.execute(
                "SELECT snapshot_json FROM assistant_turns WHERE chat_id = ? AND turn_id = ?",
                (chat_id, turn_id)).fetchone()
            if row is None:
                raise ServiceError("This request was not found in this chat.", 404)
            return json.loads(row[0])

    def save_result(self, chat_id, reference, result):
        with self.database() as connection:
            self.require_chat(connection, chat_id)
            # A graph snapshot is immutable. Narrower views have distinct references.
            connection.execute(
                "INSERT OR IGNORE INTO assistant_chat_results (chat_id, reference_json, result_json) VALUES (?, ?, ?)",
                (chat_id, encode(reference), encode(result)))

    def load_result(self, chat_id, reference):
        with self.database() as connection:
            row = connection.execute(
                "SELECT result_json FROM assistant_chat_results WHERE chat_id = ? AND reference_json = ?",
                (chat_id, encode(reference))).fetchone()
            if row is None:
                raise ServiceError("This graph was not found in the current chat.", 404, code="graph_not_found")
            return json.loads(row[0])

    def interrupt_unfinished(self):
        """Private orchestration state cannot survive a backend restart."""
        with self.database() as connection:
            rows = connection.execute(
                "SELECT sequence, snapshot_json FROM assistant_turns WHERE status IN ('running', 'needs_clarification')"
            ).fetchall()
            for row in rows:
                snapshot = json.loads(row["snapshot_json"])
                snapshot.update(status="failed", choices={},
                                text="The service restarted before this request finished. Saved graphs remain available. Send your question again.")
                connection.execute("UPDATE assistant_turns SET status = 'failed', snapshot_json = ? WHERE sequence = ?",
                                   (encode(snapshot), row["sequence"]))


CHAT_STORE = ChatStore()
