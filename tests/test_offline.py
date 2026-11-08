"""Offline tests — no API key, no internet, no model download. A fake Groq model returns fixed JSON and a fake
embedder replaces fastembed, so these test OUR code: knowledge base, safety rules, citation guard, RAG, the LangGraph
flow and SQLite persistence.
    python -m tests.test_offline
"""
import os
import tempfile

import numpy as np

from core import docs, drafting, escalation, graph, guard, kb, lang, nodes

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
PDF = lambda name: open(os.path.join(FIX, name), "rb").read()  # noqa: E731

INTAKE_PARTIAL = {"area": "deposit", "message_type": "new_facts", "title": "Deposit not returned", "summary_one_line": "Landlord not returning deposit",
                  "other_party": {"name": None, "type": "landlord"}, "place": None, "amount_inr": None, "key_dates": [],
                  "questions": ["How much was the deposit?", "Which city and state?", "When did you move out?"], "ready_for_advice": False, "risk_flags": []}
INTAKE_FULL = dict(INTAKE_PARTIAL, amount_inr=40000, other_party={"name": "Rajesh Tiwari", "type": "landlord"}, place="Varanasi, Uttar Pradesh", ready_for_advice=True, questions=[],
                   key_dates=[{"date": "1 Oct 2026", "event": "moved out"}])
ADVICE = {"case_summary": {"timeline": ["1 Oct 2026: moved out"], "evidence_have": ["agreement"], "evidence_missing": ["photos"]},
          "document_findings": ["The agreement says the deposit is refundable [DOC:1]."], "assumptions": ["Agreement is in writing"],
          "applicable_law": [{"citation": "[KB:up_tenancy_11]", "what_it_says": "refund on vacating", "how_it_applies": "you vacated"},
                             {"citation": "[LAW:Transfer of Property Act, 1882|s. 108]", "what_it_says": "lease duties", "how_it_applies": "general"}],
          "opinion": "You have a strong claim [KB:up_tenancy_11]. The old Payment of Wages Act, 1936 is irrelevant. See Sharma v. Gupta AIR 2015 SC 100.",
          "options": [{"rank": 1, "title": "WhatsApp demand", "steps": ["Send message"], "cost": "free", "time": "1 week", "citations": []}],
          "deadlines": [], "documents_needed": [], "risks": [], "uncertain": [], "see_lawyer_if": [], "refusal_note": "", "notice_explained": ""}
CALLS = []


def fake_json(messages, fast=False):
    CALLS.append(messages[0]["content"][:20])
    sysm, user = messages[0]["content"], messages[-1]["content"]
    if "intake associate" in sysm:
        convo = user.split("CONVERSATION:")[-1]
        if "neighbour" in convo:
            return dict(INTAKE_FULL, area="other")
        out = dict(INTAKE_FULL if ("40000" in convo or "40,000" in convo) else INTAKE_PARTIAL)
        if "interest" in convo.split("CLIENT:")[-1]:
            out["message_type"] = "question"
        return out
    if "follow-up question" in sysm:
        return {"answer": "You may also ask for interest [KB:ica_73] — see your agreement [DOC:1].", "suggested_questions": ["Can I email it?"]}
    if "draft documents" in sysm:
        return {"title": "Legal Notice", "body": "To [[landlord]]\\nRefund Rs 40,000 [KB:up_tenancy_11], as agreed [DOC:1]. [LAW:Indian Contract Act, 1872|s. 75]."}
    return ADVICE


def fake_embed(texts):  # hashed character trigrams — deterministic stand-in for the real embedding model
    out = np.zeros((len(texts), 256), dtype=np.float32)
    for r, t in enumerate(texts):
        t = f"  {t.lower()}  "
        for i in range(len(t) - 2):
            out[r, hash(t[i:i + 3]) % 256] += 1
    return out


def engine(path=":memory:"):
    nodes._Deps.json = fake_json
    docs._Embedder.fake = fake_embed
    return graph.Engine(path)


# ------------------------------------------------------------------ units
def test_knowledge_base():
    entries = list(kb.load().values())
    assert len({e["id"] for e in entries}) == len(entries)
    for e in entries:
        assert e["category"] in ("deposit", "consumer", "salary", "notice", "referral"), e["id"]
        assert e["confidence"] in ("high", "medium", "low") and e["source_url"].startswith("https://") and e["checked_against"].startswith("https://")
    up = [e["id"] for e in kb.for_area("deposit", "Varanasi, Uttar Pradesh")]
    pune = [e["id"] for e in kb.for_area("deposit", "Pune, Maharashtra")]
    assert "up_tenancy_11" in up and "up_tenancy_11" not in pune and "tn_tenancy_11" not in pune
    assert "ica_74" in [e["id"] for e in kb.for_area("salary", None, notice=True)]
    print(f"ok knowledge base: {len(entries)} entries, unique ids, sources, state-specific filtering")


def test_rules_and_language():
    assert lang.detect("मेरा डिपॉज़िट वापस नहीं मिला") == "hi" and lang.detect("Mera deposit wapas nahi mila bhai") == "hinglish"
    assert escalation.check("2 साल की वारंटी है")["level"] == "none"            # MISTAKES.md #7 regression
    assert escalation.check("Landlord ne mere upar FIR kar di")["level"] == "refer"
    assert escalation.check("cheque bounce ho gaya")["level"] == "refer"
    assert escalation.check("I will make his photo viral")["level"] == "refuse_part"
    assert escalation.check("I paid Rs 6 lakh for the machine")["level"] == "caution"
    print("ok safety rules + language detection")


def test_guard():
    t, r = guard.check_and_render("Pay in 2 days [KB:cow_17]. Payment of Wages Act, 1936. Raj v. Sen AIR 2010 SC 1. [KB:nope]")
    assert "✅" in t and "🔄" in t and "AIR 2010" not in t and r["unknown_kb_ids"] == ["nope"] and r["repealed"]
    print("ok citation guard: ✅ verified, 🔄 repealed, ❌ case law, unknown ids dropped")


def test_rag_store():
    eng = engine()
    info = eng.docs.add("r1", "rent.pdf", PDF("sample_rent_agreement.pdf"))
    assert info["vectors"] and info["chunks"] >= 2 and not info["duplicate"]
    assert eng.docs.add("r1", "rent.pdf", PDF("sample_rent_agreement.pdf"))["duplicate"]
    hits = eng.docs.search("r1", "when will my security deposit be refunded")
    assert hits and "vector" in hits[0]["metadata"]["via"] and hits[0]["metadata"]["cosine"] is not None
    assert eng.docs.search("other-thread", "deposit") == []
    try:
        eng.docs.add("r1", "scan.pdf", PDF("sample_blank_scan.pdf"))
        raise AssertionError("scanned PDF should be rejected")
    except docs.DocError:
        pass
    print("ok RAG store: chunks + vectors, hybrid search, dedupe, per-thread isolation, scanned PDF rejected")


# ------------------------------------------------------------------ graph flows
def test_questions_then_advice_with_document():
    eng = engine()
    eng.docs.add("t1", "rent.pdf", PDF("sample_rent_agreement.pdf"))
    st = eng.send("t1", "my landlord isn't giving my money back")
    assert st["stage"] == "questions" and "How much" in st["messages"][-1]["content"]
    st = eng.send("t1", "40000, Varanasi, moved out 1 Oct 2026")
    m = st["messages"][-1]
    assert st["stage"] == "advice", st["stage"]
    g = st["guard"]
    assert "up_tenancy_11" in g["verified"] and any("Transfer of Property" in x for x in g["ai_recalled"]) and g["repealed"] and g["case_law_removed"]
    assert "📎 *" in m["content"] and "AIR 2015" not in m["content"] and any(h["cited"] for h in m["data"]["doc_hits"])
    d = drafting.draft(st, "legal_notice", thread_id="t1")
    assert "[[VERIFY: Indian Contract Act, 1872, s. 75]]" in d["text"] and "(rent.pdf, p." in d["text"], d["text"]
    print("ok flow: questions -> advice; ✅/⚠️/🔄/❌ tiers; document cited; draft has VERIFY placeholder + document reference")


def test_always_asks_before_first_opinion():
    eng = engine()
    st = eng.send("q1", "Landlord Rajesh Tiwari in Varanasi won't return my 40000 deposit, I moved out 1 Oct 2026")
    m = st["messages"][-1]["content"]
    assert st["stage"] == "questions", st["stage"]                       # the model said ready + no questions; code still asks
    assert "What I understood so far" in m and "₹40,000" in m and "Rajesh Tiwari" in m
    assert m.count("\n1. ") == 1 and "\n2. " in m                         # fallback questions filled in by code
    assert eng.send("q1", "I have the agreement and WhatsApp chats; I want the full amount")["stage"] == "advice"
    assert nodes.missing_facts({"area": "salary", "amount_inr": 1}) == ["other_party", "dates"]
    assert nodes.missing_facts({"area": "other"}) == []
    print("ok a full story still gets one round of questions (facts shown back for correction) before the opinion")


def test_skip_and_followup():
    eng = engine()
    assert eng.send("t2", "my landlord isn't giving my money back")["stage"] == "questions"
    assert eng.send("t2", None, force_advice=True)["stage"] == "advice"
    st = eng.send("t2", "40000 Varanasi. Can I also claim interest?")
    assert st["stage"] == "answer" and "✅" in st["messages"][-1]["content"], st["stage"]
    print("ok skip questions -> advice; follow-up question -> short answer node")


def test_crisis_and_refer_without_model():
    eng = engine()
    CALLS.clear()
    assert eng.send("t3", "salary nahi mili, I want to end my life")["stage"] == "crisis"
    assert eng.send("t4", "Mere landlord ne mere upar police mein FIR kar di hai")["stage"] == "referred"
    assert not CALLS, CALLS
    st = eng.send("t5", "My neighbour's tree fell on my wall, he won't pay")
    assert st["stage"] == "referred" and "15100" in st["messages"][-1]["content"]
    print("ok crisis + refer by rules with 0 model calls; out-of-scope refer after intake")


def test_sqlite_persistence():
    path = os.path.join(tempfile.mkdtemp(), "chats.db")
    eng = engine(path)
    eng.docs.add("p1", "rent.pdf", PDF("sample_rent_agreement.pdf"))
    eng.send("p1", "40000, Varanasi, moved out 1 Oct 2026, landlord won't refund")
    eng2 = engine(path)                                                                   # = app restart
    st = eng2.state("p1")
    assert st["stage"] == "questions" and len(st["messages"]) == 2 and eng2.docs.list("p1"), st.get("stage")
    st = eng2.send("p1", None, force_advice=True)                                         # the conversation continues after restart
    assert st["stage"] == "advice" and len(st["messages"]) == 3
    eng2.delete("p1")
    assert not eng2.state("p1").get("messages") and not eng2.docs.list("p1")
    print("ok SQLite: chat + documents survive a restart; delete removes both")


if __name__ == "__main__":
    for fn in [test_knowledge_base, test_rules_and_language, test_guard, test_rag_store, test_questions_then_advice_with_document,
               test_always_asks_before_first_opinion, test_skip_and_followup, test_crisis_and_refer_without_model, test_sqlite_persistence]:
        fn()
    print("ALL OFFLINE TESTS PASSED")
