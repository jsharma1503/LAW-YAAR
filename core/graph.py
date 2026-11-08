"""LangGraph wiring + persistence.

One SQLite file (config.DB_PATH) holds everything that must survive a restart:
  • LangGraph checkpoints (SqliteSaver) — the full state of every conversation, by thread_id
  • lawyaar_threads — the sidebar list of conversations (core/threads.py)
  • doc_files / doc_chunks — uploaded PDFs as text chunks + vectors (core/docs.py)
Deleting a consultation deletes all three.
"""
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from core import config, docs, nodes


def build(checkpointer):
    g = StateGraph(nodes.CaseState)
    for name in ("screen", "intake", "ask", "advise", "answer", "crisis", "refer"):
        g.add_node(name, getattr(nodes, name))
    g.add_edge(START, "screen")
    g.add_conditional_edges("screen", nodes.route_after_screen, ["crisis", "refer", "intake", "advise"])
    g.add_conditional_edges("intake", nodes.route_after_intake, ["crisis", "refer", "ask", "advise", "answer"])
    for n in ("ask", "advise", "answer", "crisis", "refer"):
        g.add_edge(n, END)
    return g.compile(checkpointer=checkpointer)


class Engine:
    def __init__(self, db_path: str | None = None):
        path = db_path or config.DB_PATH
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: Streamlit serves from several threads; SqliteSaver and DocStore lock around their own access
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.checkpointer = SqliteSaver(self.conn)
        self.docs = docs.DocStore(sqlite3.connect(path, check_same_thread=False))  # own connection, same file
        nodes._Deps.store = self.docs
        self.graph = build(self.checkpointer)

    def send(self, thread_id: str, text: str | None, force_advice=False, lang_override=None, auto=False, attachments=None) -> dict:
        """Run one turn and return the new state of the thread."""
        msg = [{"role": "user", "content": text, "kind": "user", "data": {"auto": auto, "attachments": attachments or []}}] if text else []
        self.graph.invoke({"messages": msg, "thread_id": thread_id, "force_advice": force_advice, "lang_override": lang_override},
                          {"configurable": {"thread_id": thread_id}})
        return self.state(thread_id)

    def state(self, thread_id: str) -> dict:
        snap = self.graph.get_state({"configurable": {"thread_id": thread_id}})
        return dict(snap.values) if snap and snap.values else {}

    def append(self, thread_id: str, messages: list[dict]):
        """Save extra messages (drafts, practice summaries) into the same thread."""
        self.graph.update_state({"configurable": {"thread_id": thread_id}}, {"messages": messages}, as_node="advise")

    def delete(self, thread_id: str):
        self.checkpointer.delete_thread(thread_id)
        self.docs.delete(thread_id)
