"""Document drafting: the model writes from the case file + the client's documents; verified law renders as text;
any AI-recalled law becomes a [[VERIFY: …]] placeholder the user must check before sending."""
import datetime as dt
import io
import json

from core import docs, guard, kb, llm, nodes, prompts

SUGGEST = {"deposit": "legal_notice", "consumer": "legal_notice", "salary": "legal_notice"}


def suggested_type(case: dict) -> str:
    return "reply_to_notice" if case.get("notice_received") else SUGGEST.get(case.get("area"), "legal_notice")


def draft(state: dict, doc_type: str, thread_id: str | None = None, llm_json=None) -> dict:
    case = state.get("case") or {}
    user = (f"TODAY: {dt.date.today():%d %B %Y}\nCASE FILE: {json.dumps(case, ensure_ascii=False)}\n\n"
            f"VERIFIED LAW YOU MAY CITE:\n{kb.for_prompt(nodes._entries(case))}")
    refs = {}
    if nodes._Deps.store and thread_id:  # RAG: e.g. a reply can quote the notice it answers
        block, refs = docs.for_prompt(nodes._Deps.store.search(
            thread_id, f"{prompts.DOC_TYPES[doc_type]} {case.get('summary_one_line', '')}"))
        user += f"\n\n{block}" if block else ""
    msgs = [{"role": "system", "content": prompts.DRAFT.format(doc_type=prompts.DOC_TYPES[doc_type])}, {"role": "user", "content": user}]
    out = (llm_json or nodes._Deps.json or llm.chat_json)(msgs)
    reports = []
    body = docs.render_refs(guard.guard_obj(out.get("body", ""), reports, markdown_links=False), refs, markdown=False)
    title = out.get("title") or prompts.DOC_TYPES[doc_type]
    text = f"DRAFT — CHECK EVERY [[ ]] FIELD AND EVERY FACT BEFORE USING\n\n{title.upper()}\n\n{body}"
    if out.get("enclosures"):
        text += "\n\nEnclosures (copies):\n" + "\n".join(f"{i + 1}. {e}" for i, e in enumerate(out["enclosures"]))
    return {"doc_type": doc_type, "title": title, "text": text, "tips": out.get("sending_tips") or [], "guard": guard.merge(reports)}


def to_docx(text: str) -> bytes:
    from docx import Document
    from docx.shared import Pt
    d = Document()
    d.styles["Normal"].font.name, d.styles["Normal"].font.size = "Times New Roman", Pt(12)
    for i, block in enumerate(text.split("\n\n")):
        d.add_paragraph().add_run(block.strip()).bold = i < 2
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
