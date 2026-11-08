"""Chat page (home): welcome + suggestions when empty, then the conversation and ONE input bar (text + 🎤 + 📎 PDF)."""
import html as _html
import inspect
import json
import re
import sqlite3
import uuid

import streamlit as st
import streamlit.components.v1 as components

from core import config, docs, drafting, graph, kb, lang, llm, nodes, practice, prompts, threads, ui


@st.cache_resource(show_spinner=False)
def resources():
    return graph.Engine(), threads.Threads(sqlite3.connect(config.DB_PATH, check_same_thread=False))


ENGINE, THREADS = resources()
S, qp = st.session_state, st.query_params
# Switching pages clears URL parameters, so the private owner/thread ids also live in the session.
OWNER = S.get("owner") or qp.get("u") or uuid.uuid4().hex[:12]
S.owner = qp["u"] = OWNER
if "thread" not in S:
    S.thread = qp.get("t") or uuid.uuid4().hex[:16]
qp["t"] = S.thread
S.setdefault("prac", {})
LANGS = {"Auto-detect": None, "English": "en", "हिन्दी": "hi", "Hinglish": "hinglish"}
AREA_ICON = {"deposit": "🏠", "consumer": "🛒", "salary": "💼"}
AUTO_UPLOAD = {"en": "I have uploaded {f}. Please read it and tell me what it means for me and what I should do.",
               "hi": "मैंने {f} अपलोड किया है। कृपया पढ़कर बताइए इसका मेरे लिए क्या मतलब है और मुझे क्या करना चाहिए।",
               "hinglish": "Maine {f} upload kiya hai. Please padh ke batao iska mere liye kya matlab hai aur mujhe kya karna chahiye."}


def speakable(md: str) -> str:
    """Markdown/HTML answer -> plain sentences for the browser's text-to-speech."""
    t = re.sub(r"<[^>]+>", " ", md)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)          # [text](link) -> text
    t = re.sub(r"[*_#>`|✅⚠️🔄❌📎•]+", " ", t)
    return re.sub(r"\s+", " ", _html.unescape(t)).strip()[:6000]


def listen(md: str, language: str, key: str):
    """🔊 button: reads the answer aloud with the browser's own voices (free, nothing sent to a server)."""
    voice = "hi-IN" if language == "hi" else "en-IN"
    components.html(f"""<button id="b" style="font:13px sans-serif;border:1px solid #CC5500;background:#FFFBF2;color:#141210;
      border-radius:16px;padding:3px 12px;cursor:pointer">🔊 Listen</button>
      <script>
      const text = {json.dumps(speakable(md))}, b = document.getElementById("b"), s = window.speechSynthesis;
      b.onclick = () => {{
        if (s.speaking) {{ s.cancel(); b.textContent = "🔊 Listen"; return; }}
        const parts = text.match(/[^.!?।]+[.!?।]?/g) || [text];
        const v = s.getVoices().find(x => x.lang === "{voice}") || s.getVoices().find(x => x.lang.startsWith("{voice[:2]}"));
        parts.forEach((p, i) => {{ const u = new SpeechSynthesisUtterance(p.trim()); u.lang = "{voice}"; if (v) u.voice = v;
          u.rate = 0.95; if (i === parts.length - 1) u.onend = () => b.textContent = "🔊 Listen"; s.speak(u); }});
        b.textContent = "⏹ Stop";
      }};
      </script>""", height=38)


def new_thread():
    S.thread = qp["t"] = uuid.uuid4().hex[:16]


def send(text, force=False, auto=False, attachments=None):
    THREADS.upsert(S.thread, OWNER)
    with st.spinner("Reading your documents and reviewing your case…" if attachments else "Reviewing your case…"):
        try:
            stt = ENGINE.send(S.thread, text, force_advice=force, lang_override=LANGS[S.get("lang_pick", "Auto-detect")],
                              auto=auto, attachments=attachments)
        except llm.LLMError as e:
            st.error(str(e))
            return
    case = stt.get("case") or {}
    THREADS.upsert(S.thread, OWNER, title=case.get("title"), area=case.get("area") if case.get("area") in kb.AREAS else None)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    if st.button("＋  New consultation", type="primary", use_container_width=True):
        new_thread()
        st.rerun()
    st.markdown('<p class="ns-side-label">Your consultations</p>', unsafe_allow_html=True)
    rows = THREADS.list(OWNER)
    if not rows:
        st.caption("Your saved chats will appear here.")
    for r in rows:
        mark = "  •" if r["thread_id"] == S.thread else ""
        if st.button(f"{AREA_ICON.get(r.get('area'), '💬')}  {r['title'][:34]}{mark}", key=f"t_{r['thread_id']}", use_container_width=True):
            S.thread = qp["t"] = r["thread_id"]
            st.rerun()
    mine = ENGINE.docs.list(S.thread)
    if mine:
        st.markdown('<p class="ns-side-label">Documents in this chat</p>', unsafe_allow_html=True)
        for d in mine:
            c1, c2 = st.columns([5, 1])
            c1.caption(f"📎 {d['filename']} · {d['pages']} p · {'vectors + keywords' if d['vectors'] else 'keywords only'}")
            if c2.button("✕", key=f"rm_{d['doc_id']}", help="Remove this document"):
                ENGINE.docs.delete(S.thread, d["doc_id"])
                st.rerun()
    st.markdown('<p class="ns-side-label">Settings</p>', unsafe_allow_html=True)
    st.selectbox("Reply language", list(LANGS), key="lang_pick")
    with st.expander("Delete this consultation"):
        st.caption("Removes the chat and its uploaded documents.")
        if st.button("Delete permanently", use_container_width=True):
            ENGINE.delete(S.thread)
            THREADS.delete(S.thread, OWNER)
            new_thread()
            st.rerun()
    st.markdown(f'<p class="ns-small">Legal information, not legal advice · NALSA 15100<br>{config.model_label()}<br>'
                f'Chats saved in SQLite<br>Bookmark this page to return.</p>',
                unsafe_allow_html=True)

# ------------------------------------------------------------------ conversation
state = ENGINE.state(S.thread)
msgs = state.get("messages", [])

if not msgs:
    st.markdown(ui.WELCOME, unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 6, 1])
    with mid:
        cols = st.columns(2)
        for i, (label, text) in enumerate(ui.SUGGESTIONS):
            with cols[i % 2].container(key=f"sugg{i}"):
                if st.button(label, key=f"ex{i}", use_container_width=True, help=text):
                    send(text)
                    st.rerun()
        st.markdown(ui.WELCOME_FOOT, unsafe_allow_html=True)

for i, m in enumerate(msgs):
    d = m.get("data") or {}
    if m["role"] == "user":
        with st.chat_message("user"):
            for a in d.get("attachments", []):
                st.caption(f"📎 {a}")
            st.markdown(m["content"])
        continue
    with st.chat_message("assistant", avatar="⚖️"):
        if d.get("caution"):
            st.warning(d["caution"], icon="⚠️")
        if d.get("refusal"):
            st.info(d["refusal"], icon="🚫")
        if d.get("caselaw_note"):
            st.info(d["caselaw_note"], icon="ℹ️")
        if m.get("kind") == "draft":
            st.markdown(f"#### 📄 {d.get('title', 'Draft')}")
            edited = st.text_area("Edit before you download", m["content"], height=420, key=f"dr_{i}")
            c1, c2 = st.columns(2)
            c1.download_button("⬇ Word (.docx)", drafting.to_docx(edited), f"{d.get('doc_type', 'draft')}.docx", key=f"dx_{i}", use_container_width=True)
            c2.download_button("⬇ Text (.txt)", edited.encode(), f"{d.get('doc_type', 'draft')}.txt", key=f"dt_{i}", use_container_width=True)
            if d.get("tips"):
                st.caption("Before sending: " + " · ".join(d["tips"]))
        else:
            st.markdown(m["content"], unsafe_allow_html=True)
        if m.get("kind") in ("advice", "answer", "questions", "refer", "crisis"):
            listen(m["content"], state.get("language") or "en", f"tts_{i}")
        g = d.get("guard")
        if g:
            kbm = kb.load()
            hits = sorted(d.get("doc_hits", []), key=lambda h: not h.get("cited"))
            with st.expander(f"Sources — ✅ {len(g['verified'])} verified · ⚠️ {len(g['ai_recalled'])} to verify · "
                             f"🔄 {len(g['repealed'])} outdated · 📎 {sum(h.get('cited', False) for h in hits)} from your documents"):
                for k in g["verified"]:
                    e = kbm[k]
                    sec = str(e["section"])
                    st.markdown(f"✅ **{e['act']}**{'' if sec in ('none', 'process', 'status', 'model', 'rules') else ' — ' + ('s. ' if sec[0].isdigit() else '') + sec}"
                                f" · {e['title']} · confidence *{e['confidence']}* · [source]({e['source_url']})")
                for a in g["ai_recalled"]:
                    st.markdown(f"⚠️ **{a}** — recalled by the AI, not in the verified list. Check on [India Code](https://www.indiacode.nic.in).")
                for r in g["repealed"]:
                    st.markdown(f"🔄 **{r}** — replaced by a newer law; the answer shows the current one.")
                for h in hits:
                    sim = f" · cosine {h['cosine']}" if h.get("cosine") is not None else ""
                    st.markdown(f"📎 **{h['filename']}, page {h['page']}** · {'**cited**' if h.get('cited') else 'retrieved'} · matched by {h['via']}{sim}")
                    st.caption("“" + h["excerpt"][:300].replace("\n", " ") + "…”")
                for c in g["case_law_removed"]:
                    st.markdown(f"❌ Removed an unverifiable court-case citation: _{c[:120]}_")

stage = state.get("stage")
if stage == "questions" and st.button("⏭  Skip — advise me now with what I've told you"):
    send(None, force=True)
    st.rerun()

if stage in ("advice", "answer"):
    st.markdown('<div class="ns-eyebrow" style="margin-top:10px">Next steps</div>', unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["📄 Draft a document", "🎭 Practise the conversation", "⬇ Download case file"])
    with t1:
        types = list(prompts.DOC_TYPES)
        dt = st.selectbox("Document", types, index=types.index(drafting.suggested_type(state.get("case") or {})),
                          format_func=lambda k: prompts.DOC_TYPES[k])
        ok = st.checkbox("I checked the case summary — names, dates and amounts are correct.")
        if st.button("Draft it", type="primary", disabled=not ok):
            with st.spinner("Drafting…"):
                try:
                    dft = drafting.draft(state, dt, thread_id=S.thread)
                    ENGINE.append(S.thread, [{"role": "assistant", "kind": "draft", "content": dft["text"],
                                              "data": {"title": dft["title"], "doc_type": dt, "tips": dft["tips"], "guard": dft["guard"]}}])
                    st.rerun()
                except llm.LLMError as e:
                    st.error(str(e))
    with t2:
        hist = S.prac.setdefault(S.thread, [])
        st.caption(f"You're talking to **{practice.role(state)}** (played by AI). Be polite, specific, and give a deadline.")
        for h in hist:
            st.markdown(f"**{'You' if h['role'] == 'user' else practice.role(state)}:** {h['content']}")
        with st.form("prac", clear_on_submit=True):
            said = st.text_input("Your line", placeholder="e.g. I want my full deposit back within 7 days.")
            c1, c2 = st.columns(2)
            go = c1.form_submit_button("Say it", use_container_width=True, type="primary")
            end = c2.form_submit_button("End & get feedback", use_container_width=True, disabled=len(hist) < 2)
        try:
            if go and said:
                hist.append({"role": "user", "content": said})
                hist.append({"role": "assistant", "content": practice.reply(state, hist)})
                st.rerun()
            if end:
                fb = practice.feedback(state, hist)
                lines = "\n".join(f"- **{'You' if h['role'] == 'user' else practice.role(state)}:** {h['content']}" for h in hist)
                body = (f"#### 🎭 Practice session\n{lines}\n\n**Went well:** " + "; ".join(fb.get("went_well", []))
                        + "\n\n**Improve:** " + "; ".join(fb.get("improve", [])) + f"\n\n**Try saying:** {fb.get('try_saying', '')}")
                ENGINE.append(S.thread, [{"role": "assistant", "kind": "practice", "content": body, "data": {}}])
                S.prac[S.thread] = []
                st.rerun()
        except llm.LLMError as e:
            st.error(str(e))
    with t3:
        doc = "\n\n---\n\n".join(("**You:** " + m["content"]) if m["role"] == "user" else nodes.full_markdown(m) for m in msgs)
        st.download_button("Download the full consultation (.md)", doc.encode(), "lawyaar_case.md", use_container_width=True)

# ------------------------------------------------------------------ ONE input bar: text + 🎤 mic + 📎 PDF  (Streamlit ≥ 1.52)
CI = inspect.signature(st.chat_input).parameters
kw = {"accept_file": "multiple", "file_type": ["pdf"]} if "accept_file" in CI else {}
kw |= {"accept_audio": True, "audio_sample_rate": 16000} if "accept_audio" in CI else {}
val = st.chat_input("Describe your problem, tap 🎤 to speak, or 📎 attach a PDF… / अपनी समस्या बताइए…", **kw)
old_audio = None
if "accept_audio" not in CI:
    st.warning(f"Streamlit {st.__version__} can't show the mic inside the text bar — run `pip install -U streamlit`. "
               "Using a separate recorder for now.", icon="🎤")
    old_audio = st.audio_input("Speak", key=f"aud_{len(msgs)}")
host = st.context.headers.get("host") or ""
if "accept_audio" in CI and re.match(r"^\d+\.\d+\.\d+\.\d+", host) and not host.startswith("127."):
    st.caption(f"🎤 Browsers allow the microphone only on https or localhost — open **http://localhost:{host.split(':')[-1]}** to use voice.")

if val or old_audio is not None:
    field = (lambda k: None) if val is None or isinstance(val, str) else (lambda k: getattr(val, k, None))
    text = val if isinstance(val, str) else (field("text") or "")
    audio = old_audio if old_audio is not None else field("audio")
    if audio is not None:
        with st.spinner("Listening… / सुन रहा हूँ…"):
            try:
                heard = llm.transcribe(audio.getvalue())
                text = f"{text} {heard}".strip()
                st.toast(f"🎤 {heard[:90]}")
            except llm.LLMError as e:
                st.error(str(e))
    attached = []
    for f in field("files") or []:
        try:
            with st.spinner(f"Reading {f.name} and building its search index…"):
                info = ENGINE.docs.add(S.thread, f.name, f.getvalue())
            if info["duplicate"]:
                st.toast(f"{f.name} is already in this consultation")
            else:
                attached.append(f"{f.name} ({info['pages']} pages)")
        except docs.DocError as e:
            st.error(f"{f.name}: {e}")
    auto = bool(attached and not text)
    if auto:
        prev = [m["content"] for m in msgs if m["role"] == "user"]
        lg = LANGS[S.get("lang_pick", "Auto-detect")] or (lang.detect(prev[-1]) if prev else "en")
        text = AUTO_UPLOAD[lg].format(f=", ".join(a.split(" (")[0] for a in attached))
    if text:
        send(text, auto=auto, attachments=attached)
        st.rerun()
