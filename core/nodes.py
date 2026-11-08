"""LangGraph nodes (state in -> partial update out). Wiring is in core/graph.py.

    screen  [code] language + safety rules ───────────────► crisis | refer   (fixed messages, 0 model calls)
    intake  [LLM fast] update case file from chat + documents; decide questions; flags ─► refer if outside the 4 problems
    ask     [code] questions before the first opinion: always ≥1 round, required facts checked in code, max 2 rounds, skippable
    advise  [LLM]  opinion grounded in verified KB + the client's documents (RAG) ─► [code] citation guard
    answer  [LLM fast] short answer to a follow-up question on an advised case
"""
import json
import operator
from typing import Annotated, TypedDict

from core import docs, escalation, guard, kb, lang, llm, prompts, referral

MIN_QUESTION_ROUNDS = 1   # a lawyer always asks before advising: at least one round of questions, unless the user skips
MAX_QUESTION_ROUNDS = 2   # ...and never more than two, so the user isn't interrogated

# Facts the opinion cannot be written responsibly without — checked in CODE, not left to the model's "ready" flag.
REQUIRED = {"deposit": ["place", "amount", "dates", "other_party"],
            "consumer": ["what", "amount", "dates", "other_party"],
            "salary": ["other_party", "amount", "dates"]}
FALLBACK_Q = {
    "en": {"place": "Which city and state is the property in? (Tenancy rules depend on the state.)",
           "amount": "What is the exact amount involved, in rupees?",
           "dates": "What are the key dates — e.g. when you moved out / bought it / last got paid?",
           "other_party": "Who is the other side — their name, or the company / seller / landlord?",
           "what": "What exactly did you buy or pay for, and from which shop or website?",
           "proof": "What do you have in writing — agreement, invoice, payslips, chats, emails?",
           "tried": "What have you already done — called, emailed, complained? What did they reply?",
           "outcome": "What outcome do you want — full refund, replacement, payment, compensation?"},
    "hi": {"place": "मकान किस शहर और राज्य में है? (किराए के नियम राज्य पर निर्भर हैं।)",
           "amount": "कुल कितनी रकम का मामला है (रुपये में)?",
           "dates": "ज़रूरी तारीखें क्या हैं — जैसे घर कब खाली किया / सामान कब खरीदा / आखिरी वेतन कब मिला?",
           "other_party": "दूसरा पक्ष कौन है — नाम, या कंपनी / दुकान / मकान मालिक?",
           "what": "आपने ठीक-ठीक क्या खरीदा या किस सेवा का भुगतान किया, किस दुकान या वेबसाइट से?",
           "proof": "आपके पास लिखित में क्या है — एग्रीमेंट, बिल, सैलरी स्लिप, चैट, ईमेल?",
           "tried": "आपने अब तक क्या किया है — फ़ोन, ईमेल, शिकायत? उन्होंने क्या जवाब दिया?",
           "outcome": "आप क्या चाहते हैं — पूरा रिफ़ंड, बदलाव, भुगतान, या हर्जाना?"},
    "hinglish": {"place": "Ghar kis city aur state mein hai? (Rent ke rules state pe depend karte hain.)",
                 "amount": "Exact kitne rupaye ka matter hai?",
                 "dates": "Important dates kya hain — jaise ghar kab khaali kiya / kab kharida / last salary kab mili?",
                 "other_party": "Doosri side kaun hai — naam, ya company / seller / landlord?",
                 "what": "Aapne exactly kya kharida ya kis service ke paise diye, kis shop ya website se?",
                 "proof": "Aapke paas likhit mein kya hai — agreement, bill, payslips, chats, emails?",
                 "tried": "Aapne ab tak kya kiya hai — call, email, complaint? Unhone kya jawab diya?",
                 "outcome": "Aapko kya chahiye — full refund, replacement, payment ya compensation?"},
}


def missing_facts(case: dict) -> list[str]:
    """Required facts for this area that the case file still lacks (empty for out-of-scope areas)."""
    have = {"place": bool(case.get("place")), "amount": case.get("amount_inr") not in (None, "", 0),
            "dates": bool(case.get("key_dates")), "other_party": bool((case.get("other_party") or {}).get("name")),
            "what": bool(case.get("summary_one_line") or case.get("title"))}
    return [f for f in REQUIRED.get(case.get("area"), []) if not have[f]]


def questions_for(case: dict, lg: str) -> list[str]:
    """The model's questions, topped up in code: never zero questions, and missing required facts are always asked."""
    qs = [q for q in (case.get("questions") or []) if isinstance(q, str) and q.strip()][:4]
    fb = FALLBACK_Q.get(lg, FALLBACK_Q["en"])
    blob = " ".join(qs).lower()
    hints = {"place": ("city", "state", "शहर", "राज्य"), "amount": ("amount", "rs", "₹", "rupee", "रकम", "rupaye", "kitne"),
             "dates": ("date", "when", "kab", "तारीख", "कब"), "other_party": ("name", "who", "company", "naam", "नाम", "कौन"),
             "what": ("what did you buy", "product", "kya kharida", "क्या खरीदा")}
    for f in missing_facts(case):
        if len(qs) < 4 and not any(h in blob for h in hints[f]):
            qs.append(fb[f])
    for f in ("proof", "tried", "outcome"):   # what a careful lawyer always confirms
        if len(qs) < 2:
            qs.append(fb[f])
    return qs
AREA_NAMES = {"deposit": "security deposit not returned by the landlord", "consumer": "consumer refund / defective product / order not delivered",
              "salary": "unpaid salary or withheld full-and-final settlement"}


class CaseState(TypedDict, total=False):
    messages: Annotated[list, operator.add]   # {"role", "content", "kind", "data"}
    thread_id: str
    case: dict
    language: str
    lang_override: str | None
    escalation: dict
    stage: str
    advice: dict
    guard: dict
    question_rounds: int
    force_advice: bool
    llm_calls: int


class _Deps:  # set by graph.Engine; tests swap in fakes
    store: docs.DocStore | None = None
    json = None


def _json(messages, config, fast=False, max_tokens=2500):
    if _Deps.json:
        return _Deps.json(messages, fast=fast)
    return llm.chat_json(messages, fast=fast, max_tokens=max_tokens, config_=config)


def _user_texts(state, typed_only=False) -> list[str]:
    return [m["content"] for m in state.get("messages", [])
            if m.get("role") == "user" and m.get("content") and not (typed_only and (m.get("data") or {}).get("auto"))]


def _doc_context(state, query_extra: str = ""):
    """RAG: search this consultation's PDFs with the latest message + English case summary."""
    if not _Deps.store or not state.get("thread_id"):
        return "", {}, []
    texts = _user_texts(state)
    case = state.get("case") or {}
    query = " ".join([texts[-1] if texts else "", case.get("summary_one_line") or "", query_extra]).strip()
    hits = _Deps.store.search(state["thread_id"], query or "agreement amount date")
    block, refs = docs.for_prompt(hits)
    shown = [{"n": n, **h["metadata"], "excerpt": h["page_content"][:400]} for n, h in enumerate(hits, 1)]
    return block, refs, shown


def _with_cited(shown: list, raw) -> list:
    used = docs.cited(raw)
    return [dict(h, cited=h["n"] in used) for h in shown]


def _msg(kind: str, content: str, data: dict, config) -> dict:
    return {"role": "assistant", "kind": kind, "content": content, "data": dict(data)}


def _entries(case: dict) -> list[dict]:
    return kb.for_area(case.get("area"), case.get("place"), bool(case.get("notice_received")))


# ------------------------------------------------------------------ nodes
def screen(state: CaseState) -> dict:
    typed = _user_texts(state, typed_only=True)
    lg = state.get("lang_override") or lang.detect(typed[-1] if typed else "")
    return {"language": lg, "escalation": escalation.check("\n".join(_user_texts(state)))}


def route_after_screen(state: CaseState) -> str:
    level = state["escalation"]["level"]
    if level in ("crisis", "refer"):
        return level
    if state.get("force_advice") and state.get("case"):
        return "advise"  # "skip questions": no new facts, so no new intake call
    return "intake"


def crisis(state: CaseState, config=None) -> dict:
    return {"stage": "crisis", "force_advice": False,
            "messages": [_msg("crisis", referral.crisis_message(state["language"]), {}, config)]}


def refer(state: CaseState, config=None) -> dict:
    lg = state["language"]
    body = referral.refer_message(state["escalation"]["reasons"], lg) + f"\n\n_{LABELS[lg]['disclaimer']}_"
    return {"stage": "referred", "force_advice": False,
            "messages": [_msg("refer", body, {}, config)]}


def intake(state: CaseState, config=None) -> dict:
    lg = state["language"]
    convo = [f"CLIENT: {m['content']}" if m["role"] == "user" else f"ASSISTANT ASKED: {m['content'][:500]}"
             for m in state.get("messages", []) if m["role"] == "user" or m.get("kind") == "questions"]
    doc_block, _, _ = _doc_context(state, "agreement amount deposit salary refund date notice")
    user = (f"CURRENT CASE FILE:\n{json.dumps(state.get('case') or {}, ensure_ascii=False)}\n\nCONVERSATION:\n" + "\n".join(convo)
            + (f"\n\n{doc_block}" if doc_block else ""))
    case = _json([{"role": "system", "content": prompts.INTAKE.replace("{lang_name}", lang.NAMES[lg])},
                  {"role": "user", "content": user}], config, fast=True, max_tokens=1800)
    flags = list(case.get("risk_flags") or []) + (["out_of_scope"] if case.get("area") not in kb.AREAS else [])
    esc = escalation.check("\n".join(_user_texts(state)), flags, case.get("amount_inr"))
    return {"case": case, "escalation": esc, "llm_calls": state.get("llm_calls", 0) + 1}


def route_after_intake(state: CaseState) -> str:
    level, case = state["escalation"]["level"], state.get("case") or {}
    if level in ("crisis", "refer"):
        return level
    if case.get("message_type") == "question" and state.get("stage") in ("advice", "answer"):
        return "answer"
    rounds = state.get("question_rounds", 0)
    if state.get("force_advice") or rounds >= MAX_QUESTION_ROUNDS or state.get("stage") in ("advice", "answer"):
        return "advise"          # user skipped, enough rounds, or new facts for an already-advised case -> (re)advise
    if rounds < MIN_QUESTION_ROUNDS:
        return "ask"             # always ask once before the first opinion — the model's "ready" flag can't skip this
    if missing_facts(case) or (case.get("questions") and not case.get("ready_for_advice")):
        return "ask"
    return "advise"


def ask(state: CaseState, config=None) -> dict:
    lg, case, L = state["language"], state.get("case") or {}, LABELS[state["language"]]
    parts = []
    facts = [(L["f_problem"], case.get("summary_one_line")), (L["f_party"], (case.get("other_party") or {}).get("name")),
             (L["f_place"], case.get("place")),
             (L["f_amount"], f"₹{case['amount_inr']:,.0f}" if isinstance(case.get("amount_inr"), (int, float)) else None),
             (L["f_dates"], "; ".join(f"{d.get('date')} — {d.get('event')}" for d in (case.get("key_dates") or [])[:4]
                                     if isinstance(d, dict)) or None),
             (L["f_proof"], ", ".join(case.get("evidence_have") or []) or None)]
    known = [f"- **{k}:** {v}" for k, v in facts if v]
    if known:
        parts.append(f"**{L['understood']}** _{L['correct_me']}_\n" + "\n".join(known))
    parts.append(f"#### {L['questions']}\n" + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions_for(case, lg))))
    parts.append(f"_{L['skip_hint']}_")
    return {"stage": "questions", "question_rounds": state.get("question_rounds", 0) + 1, "force_advice": False,
            "messages": [_msg("questions", "\n\n".join(parts), banners(state), config)]}


def advise(state: CaseState, config=None) -> dict:
    lg, case, esc = state["language"], state.get("case") or {}, state["escalation"]
    doc_block, refs, shown = _doc_context(state)
    block = (f"CASE FILE (JSON):\n{json.dumps(case, ensure_ascii=False)}\n\nCLIENT'S OWN WORDS:\n" + "\n".join(_user_texts(state))
             + f"\n\nSAFETY FLAGS FROM RULES: {esc['reasons'] or 'none'}\n\nVERIFIED KNOWLEDGE-BASE ENTRIES (cite as [KB:id]):\n"
             + kb.for_prompt(_entries(case)) + (f"\n\n{doc_block}" if doc_block else ""))
    system = (prompts.ADVISE.replace("{area}", AREA_NAMES.get(case.get("area"), "")).replace("{lang_instruction}", lang.instruction(lg)))
    raw = _json([{"role": "system", "content": system}, {"role": "user", "content": block}], config, max_tokens=3000)
    reports = []
    adv = docs.render_refs(guard.guard_obj(raw, reports), refs)
    g = guard.merge(reports)
    data = banners(state) | {"refusal": adv.get("refusal_note") or "", "guard": g, "doc_hits": _with_cited(shown, raw)}
    return {"stage": "advice", "advice": adv, "guard": g, "force_advice": False, "llm_calls": state.get("llm_calls", 0) + 1,
            "messages": [_msg("advice", render_advice(adv, lg), data, config)]}


def answer(state: CaseState, config=None) -> dict:
    lg, case, L = state["language"], state.get("case") or {}, LABELS[state["language"]]
    texts = _user_texts(state)
    doc_block, refs, shown = _doc_context(state)
    block = (f"CASE FILE (JSON):\n{json.dumps(case, ensure_ascii=False)}\n\nEARLIER OPINION: "
             f"{str((state.get('advice') or {}).get('opinion', ''))[:1500]}\n\nCLIENT'S QUESTION: {texts[-1] if texts else ''}\n\n"
             f"VERIFIED KNOWLEDGE-BASE ENTRIES (cite as [KB:id]):\n{kb.for_prompt(_entries(case))}" + (f"\n\n{doc_block}" if doc_block else ""))
    system = prompts.ANSWER.replace("{area}", AREA_NAMES.get(case.get("area"), "")).replace("{lang_instruction}", lang.instruction(lg))
    raw = _json([{"role": "system", "content": system}, {"role": "user", "content": block}], config, fast=True, max_tokens=1500)
    reports = []
    out = docs.render_refs(guard.guard_obj(raw, reports), refs)
    body = str(out.get("answer", ""))
    if out.get("suggested_questions"):
        body += f"\n\n**{L['next_q']}**\n" + _b(out["suggested_questions"])
    body += f"\n\n<small>{L['legend']}</small>"
    g = guard.merge(reports)
    return {"stage": "answer", "guard": g, "force_advice": False, "llm_calls": state.get("llm_calls", 0) + 1,
            "messages": [_msg("answer", body, banners(state) | {"guard": g, "doc_hits": _with_cited(shown, raw)}, config)]}


# ------------------------------------------------------------------ rendering
def banners(state: CaseState) -> dict:
    esc, lg = state["escalation"], state["language"]
    return {"caution": referral.caution_banner(esc["reasons"], lg),
            "caselaw_note": LABELS[lg]["caselaw"] if esc.get("case_law_requested") else None}


def _b(items) -> str:
    return "\n".join(f"- {x}" for x in (items or []) if x)


def render_advice(a: dict, lg: str) -> str:
    L, out = LABELS[lg], []
    cs = a.get("case_summary") or {}
    out.append(f"#### {L['summary']}\n**{L['timeline']}**\n{_b(cs.get('timeline'))}\n\n**{L['have']}**\n{_b(cs.get('evidence_have'))}"
               f"\n\n**{L['missing']}**\n{_b(cs.get('evidence_missing'))}")
    if a.get("notice_explained"):
        out.append(f"#### {L['notice']}\n{a['notice_explained']}")
    for key in ("document_findings", "assumptions"):
        if a.get(key):
            out.append(f"#### {L[key]}\n{_b(a[key])}")
    if a.get("applicable_law"):
        out.append(f"#### {L['law']}\n" + "\n".join(f"- {x.get('citation', '')} — {x.get('what_it_says', '')}  \n  ↳ *{x.get('how_it_applies', '')}*"
                                                   for x in a["applicable_law"]))
    out.append(f"#### {L['opinion']}\n{a.get('opinion', '')}")
    if a.get("options"):
        out.append(f"#### {L['options']}\n" + "\n\n".join(
            f"**{o.get('rank', '')}. {o.get('title', '')}** · {L['cost']}: {o.get('cost', '?')} · {L['time']}: {o.get('time', '?')}\n{_b(o.get('steps'))}"
            for o in a["options"]))
    for key in ("deadlines", "documents_needed", "risks", "uncertain", "see_lawyer_if"):
        if a.get(key):
            out.append(f"#### {L[key]}\n{_b(a[key])}")
    out.append(f"<small>{L['legend']}</small>\n\n_{L['disclaimer']}_")
    return "\n\n".join(out)


def full_markdown(msg: dict) -> str:
    d = msg.get("data") or {}
    parts = [f"> ⚠️ {d['caution']}"] if d.get("caution") else []
    parts += [f"> 🚫 {d['refusal']}"] if d.get("refusal") else []
    parts += [f"> ℹ️ {d['caselaw_note']}"] if d.get("caselaw_note") else []
    return "\n\n".join(parts + [msg["content"]])


LABELS = {
    "en": {"f_problem": "Problem", "f_party": "Other side", "f_place": "Place", "f_amount": "Amount", "f_dates": "Dates", "f_proof": "Proof you mentioned", "correct_me": "(correct me if anything is wrong)", "summary": "Case summary", "timeline": "What happened", "have": "Proof you have", "missing": "Proof to collect",
           "notice": "The notice you received", "document_findings": "What your documents show", "assumptions": "Assumptions I made",
           "law": "Applicable law", "opinion": "Opinion — where you stand", "options": "Your options (easiest first)",
           "deadlines": "Time limits", "documents_needed": "Keep these ready", "risks": "What the other side may say",
           "uncertain": "What I'm not sure about", "see_lawyer_if": "Get a lawyer if", "cost": "Cost", "time": "Time",
           "questions": "A few questions before I advise you", "understood": "What I understood so far", "next_q": "You could also ask",
           "skip_hint": "Answer what you can — or press “Skip — advise me now”.",
           "caselaw": "I don't quote court judgments: AI tools often invent them and I can't verify them. A lawyer can find the right ones.",
           "legend": "✅ verified source · ⚠️ AI-recalled — check on indiacode.nic.in · 🔄 old law that was replaced · 📎 your document",
           "disclaimer": "Legal information, not legal advice. Verify important steps with a lawyer or free legal aid (NALSA 15100)."},
    "hi": {"f_problem": "समस्या", "f_party": "दूसरा पक्ष", "f_place": "जगह", "f_amount": "रकम", "f_dates": "तारीखें", "f_proof": "आपके बताए सबूत", "correct_me": "(कुछ गलत हो तो बताइए)", "summary": "मामले का सार", "timeline": "क्या हुआ", "have": "आपके पास सबूत", "missing": "जुटाने लायक सबूत",
           "notice": "आपको मिला नोटिस", "document_findings": "आपके दस्तावेज़ क्या बताते हैं", "assumptions": "मैंने ये मान लिया है",
           "law": "लागू कानून", "opinion": "राय — आपकी स्थिति", "options": "आपके विकल्प (आसान से कठिन)",
           "deadlines": "समय-सीमा", "documents_needed": "ये कागज़ तैयार रखें", "risks": "दूसरा पक्ष क्या कह सकता है",
           "uncertain": "जिसके बारे में मैं पक्का नहीं हूँ", "see_lawyer_if": "वकील से मिलें अगर", "cost": "खर्च", "time": "समय",
           "questions": "सलाह से पहले कुछ सवाल", "understood": "मैंने क्या समझा", "next_q": "आप यह भी पूछ सकते हैं",
           "skip_hint": "जितना पता हो बताएँ — या “अभी सलाह दें” दबाएँ।",
           "caselaw": "मैं अदालती फ़ैसलों का हवाला नहीं देता: AI अक्सर नकली केस बना देता है। वकील सही फ़ैसले ढूँढ सकते हैं।",
           "legend": "✅ जाँचा हुआ स्रोत · ⚠️ AI की याद से — indiacode.nic.in पर जाँचें · 🔄 बदला हुआ पुराना कानून · 📎 आपका दस्तावेज़",
           "disclaimer": "यह कानूनी जानकारी है, कानूनी सलाह नहीं। ज़रूरी कदम वकील या मुफ़्त कानूनी सहायता (NALSA 15100) से जाँच लें।"},
    "hinglish": {"f_problem": "Problem", "f_party": "Doosri side", "f_place": "Jagah", "f_amount": "Amount", "f_dates": "Dates", "f_proof": "Aapke bataye proof", "correct_me": "(kuch galat ho to batayein)", "summary": "Case summary", "timeline": "Kya hua", "have": "Aapke paas proof", "missing": "Jo proof jutaana hai",
                 "notice": "Aapko mila notice", "document_findings": "Aapke documents kya batate hain", "assumptions": "Maine ye maan liya hai",
                 "law": "Lagu kanoon", "opinion": "Opinion — aap kahan khade hain", "options": "Aapke options (aasaan se mushkil)",
                 "deadlines": "Time limits", "documents_needed": "Ye documents ready rakhein", "risks": "Doosri side kya bol sakti hai",
                 "uncertain": "Jiske baare mein main pakka nahi hoon", "see_lawyer_if": "Lawyer se milein agar", "cost": "Kharcha", "time": "Time",
                 "questions": "Advice se pehle kuch sawaal", "understood": "Maine kya samjha", "next_q": "Aap ye bhi pooch sakte hain",
                 "skip_hint": "Jitna pata ho batayein — ya “Skip — abhi advice do” dabayein.",
                 "caselaw": "Main court judgments quote nahi karta: AI aksar fake cases bana deta hai. Lawyer sahi judgments dhoondh sakte hain.",
                 "legend": "✅ verified source · ⚠️ AI-recalled — indiacode.nic.in pe check karein · 🔄 purana badla hua kanoon · 📎 aapka document",
                 "disclaimer": "Yeh legal information hai, legal advice nahi. Zaroori steps lawyer ya free legal aid (NALSA 15100) se confirm karein."},
}
