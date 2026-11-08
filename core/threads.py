"""Conversation list for the sidebar: one row per LangGraph thread, in the same SQLite file as the checkpoints.
Each browser gets an anonymous owner id (kept in the URL and session), so visitors only see their own chats."""
import sqlite3
import threading

DDL = """CREATE TABLE IF NOT EXISTS lawyaar_threads (
    thread_id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL DEFAULT 'New consultation', area TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS lawyaar_threads_owner ON lawyaar_threads (owner, updated_at DESC);"""


class Threads:
    def __init__(self, conn: sqlite3.Connection):
        self.conn, self.lock = conn, threading.Lock()
        with self.lock:
            conn.executescript(DDL)
            conn.commit()

    def upsert(self, thread_id, owner, title=None, area=None):
        with self.lock:
            self.conn.execute("""INSERT INTO lawyaar_threads (thread_id, owner, title, area) VALUES (?, ?, COALESCE(?, 'New consultation'), ?)
                ON CONFLICT(thread_id) DO UPDATE SET updated_at = datetime('now'),
                title = COALESCE(?, lawyaar_threads.title), area = COALESCE(?, lawyaar_threads.area)""", (thread_id, owner, title, area, title, area))
            self.conn.commit()

    def list(self, owner, limit=40):
        with self.lock:
            rows = self.conn.execute("SELECT thread_id, title, area FROM lawyaar_threads WHERE owner=? ORDER BY updated_at DESC LIMIT ?",
                                     (owner, limit)).fetchall()
        return [{"thread_id": r[0], "title": r[1], "area": r[2]} for r in rows]

    def delete(self, thread_id, owner):
        with self.lock:
            self.conn.execute("DELETE FROM lawyaar_threads WHERE thread_id=? AND owner=?", (thread_id, owner))
            self.conn.commit()
