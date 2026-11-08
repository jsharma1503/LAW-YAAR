# ⚖️ LAW-YAAR — stand up for what's yours. AI legal help for four everyday problems in India

Talk to it in **one input bar — type, tap 🎤 to speak, or 📎 attach a PDF** — in **English, Hindi or Hinglish**.

| It handles | It refers you to free legal aid (NALSA 15100 / DLSA) for |
|---|---|
| 🏠 Landlord not returning the **security deposit** | Police/FIR/arrest, court summons, cheque bounce |
| 🛒 **Refund** not received · defective product · order not delivered | Divorce, custody, domestic violence (+112 / 181) |
| 💼 **Salary** unpaid · full-and-final settlement / gratuity withheld | Land, inheritance, builder disputes |
| 📨 A **notice you received** about one of these | Cyber fraud (+1930) · self-harm → Tele-MANAS 14416 |

What it does: **asks** the questions a lawyer would ask → writes a short **opinion** (case summary, applicable law with citations, options from cheapest to formal, deadlines, risks) → **reads your PDFs** and quotes the page → **drafts** a WhatsApp demand, legal notice, reply to a notice, consumer complaint or wage-claim application (.docx) → lets you **practise** with the other side → 🔊 **reads answers aloud** (browser voices, Hindi or English, free).

> Legal information, not legal advice. Knowledge base checked on 8 Nov 2026 (`kb/knowledge_base.yaml`). Real mistakes found while building: `MISTAKES.md`.

## How it works
```
 text / 🎤 Groq Whisper / 📎 PDF ─► RAG index (SQLite: chunks + vectors)
        │
        ▼
 screen [code] language + safety rules ──────► crisis / refer  (fixed messages, no model call)
        ▼
 intake [Groq gpt-oss-20b] case file from chat + document excerpts; out of scope? ─► refer
        ├──► ask     [code]  ALWAYS ≥1 round of questions before the first opinion; required facts per problem
        │                    checked in code (place, amount, dates, other side); shows "what I understood" for correction; max 2 rounds, skippable
        ├──► advise  [Groq gpt-oss-120b] opinion from VERIFIED KB + [DOC:n] excerpts ─► citation guard [code]
        └──► answer  [Groq gpt-oss-20b] short answer to a follow-up question
 every node checkpointed in SQLite by thread_id
```
| LLM | Code / rules | Human in the loop |
|---|---|---|
| Understands the story, decides questions | Safety rules, scope, routing, KB retrieval, document search | User answers/skips questions |
| Writes opinion, answers, drafts, role-play | Citation guard, repealed-law check, helpline messages | Ticks "facts are correct" before any draft; fills `[[ ]]` |
| | Persistence, thread list | |

**Not inventing law.** (1) A small knowledge base of 28 entries, each checked against the section text, with a source and a confidence level. (2) The model cites them only as tokens like `[KB:cow_17]`, and code turns those into ✅ links. (3) Anything else the model cites must use `[LAW:…]` and is shown as ⚠️ *verify*; in drafts it becomes `[[VERIFY: …]]`. (4) Repealed laws (Payment of Wages Act, Consumer Protection Act 1986, IPC…) are caught and shown 🔄 with their replacement. (5) Court-case citations are removed ❌.

**Documents (RAG).** A PDF is split into page-tagged chunks. Each chunk gets a **multilingual embedding** (fastembed MiniLM, local and free), stored as a vector in SQLite. Search is **hybrid**: vector cosine plus BM25 keywords, merged by Reciprocal Rank Fusion. Each consultation only ever searches its own documents. Answers cite pages (📎 *rent.pdf, p. 2*), and the Sources panel shows the excerpt and whether it matched by vector, keyword or both. Duplicate uploads are skipped; scanned PDFs get a clear message (no OCR). Document text is treated as evidence, never as instructions.

**Chat history.** One SQLite file (`data/lawyaar.db`) holds three things:
- LangGraph checkpoints (`SqliteSaver`), the full state of each thread;
- the sidebar's thread list;
- the document index.

Each browser gets a private link (`?u=…`). Deleting a consultation deletes its chat and its documents.

## Run locally
```bash
python -m venv .venv && .venv\Scripts\activate          # Mac/Linux: source .venv/bin/activate
pip install -U -r requirements.txt
copy .env.example .env                                  # Mac/Linux: cp — then add GROQ_API_KEY
python -m tests.test_offline                            # no keys needed
streamlit run app.py                                    # open http://localhost:8501 (the mic needs localhost or https)
```
Key: **Groq** → https://console.groq.com/keys

## Deploy (Streamlit Community Cloud) — full steps in DEPLOY.md
1. Push the repo to GitHub as public (`.env` and `data/` are git-ignored).
2. Go to https://share.streamlit.io → Create app → `app.py`.
3. In Secrets, paste the keys from `.streamlit/secrets.toml.example`.

Limits on the free hosting:
- The SQLite file is reset when the app restarts or sleeps. That's fine for a demo; for real users, swap `SqliteSaver` for a hosted database saver.
- The local embedding model needs about 500 MB of RAM. If the app runs out of memory, search falls back to keywords only.

## Change the model
Set `GROQ_MODEL` (opinions and drafts) and `GROQ_FAST_MODEL` (intake, follow-ups, practice) to any Groq chat model. Nothing else in the code names a model.

## Tests and raw outputs
```bash
python run_tests.py                  # 26 cases → raw_outputs/<timestamp>_<model>/ (.json + .md per case, SUMMARY.md)
python run_tests.py --ids 01 13 25   # subset
```
The 26 cases are:
- 10 realistic cases across the 4 problems, in English, Hindi and Hinglish;
- 3 with PDFs: a rent agreement, a legal notice received, and an offer letter plus a follow-up question;
- 6 adversarial: a case-law request, "make up a section", missing facts over two turns, harassment intent, the user citing IPC, and a crisis;
- 7 out of scope, which must be referred: FIR against the user, a ₹72 lakh builder dispute, a court summons, cheque bounce, domestic violence, RTI and cyber fraud.

Automatic checks:
- stage, safety level, area and reply language;
- whether the answer cites law, and whether it cites the uploaded document;
- that no case law or unflagged repealed law reaches the user;
- the share of citations that came from the verified knowledge base.

In-scope cases are expected to get questions first (`asked_before_advising`). The runner then answers the way a user can — by pressing **Skip** (`"__SKIP__"` in `cases.json`, or automatically when the scripted messages run out; the JSON records `auto_skipped`).

Groq's free tier allows about 8K tokens per minute per model, so the runner waits 30 s between cases. Run the suite in batches with `--ids`.

## Files
```
app.py                    entry: theme, logo, the single chat page
views/chat.py             the app: welcome + 4 examples, ONE input bar (text 🎤 📎), sidebar threads + documents, sources, drafts, practice, 🔊
core/config.py            settings (.env / Streamlit secrets → environment)
core/llm.py               Groq only: ChatGroq (chat, JSON) + Groq Whisper
core/graph.py             LangGraph StateGraph + SqliteSaver + document store
core/nodes.py             screen · intake · ask · advise · answer · refer · crisis
core/docs.py              RAG: PDF → chunks → embeddings → SQLite vectors → hybrid search
core/kb.py  kb/*.yaml     verified knowledge base (28 entries, 4 areas)
core/guard.py             ✅ / ⚠️ / 🔄 / ❌ citation labelling
core/escalation.py        safety rules · core/referral.py fixed helpline messages
core/drafting.py core/practice.py core/prompts.py core/lang.py core/threads.py core/ui.py
tests/                    test_offline.py, cases.json (26), fixtures/ (fictional PDFs), make_sample_pdfs.py
run_tests.py              batch runner → raw_outputs/
collect_results.py        combines all runs → raw_outputs/ALL_SUMMARY.md + numbers for the solution doc
RUN_GUIDE.md              step-by-step: setup → tests → filling the solution doc → submission
```

## Known limits
- **Tenancy is state law.** Only Uttar Pradesh and Tamil Nadu have state-specific entries; for other states the answer says the rules depend on the state and the rent agreement.
- **The safety rules are keyword-based**, so they can over- or under-trigger (see MISTAKES.md #7, #9, #10).
- **No OCR**, so scanned PDFs aren't read. Hindi PDFs with non-Unicode fonts may extract as garbled text.
- **The private chat link isn't real login.** Don't share your link.
