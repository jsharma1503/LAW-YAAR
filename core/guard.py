"""Citation guard — every legal reference the user sees gets a trust label.

  [KB:id]                 -> ✅ VERIFIED   (curated knowledge base, official link)
  [LAW:Act, Year|s. 12]   -> ⚠️ AI-RECALLED (shown, but marked "verify"; upgraded to ✅ if it matches the KB)
  repealed law (IPC, CrPC, Payment of Wages Act…) -> 🔄 flagged with its replacement (and new section if known)
  court-case citations    -> ❌ removed (cannot be verified; models invent them)
  untagged Acts/sections in prose -> treated like AI-recalled (marked inline)
"""
import re

from core import kb

# Laws a model may still cite from old training data -> what replaced them (checked 2026-11-08)
REPEALED = [
    (r"payment of wages act|minimum wages act|payment of bonus act|equal remuneration act", "Code on Wages, 2019", "21 Nov 2025"),
    (r"payment of gratuity act", "Code on Social Security, 2020", "21 Nov 2025"),
    (r"industrial disputes act", "Industrial Relations Code, 2020", "21 Nov 2025"),
    (r"consumer protection act,? 1986", "Consumer Protection Act, 2019", "20 July 2020"),
    (r"indian penal code|\bipc\b", "Bharatiya Nyaya Sanhita, 2023", "1 July 2024"),
    (r"code of criminal procedure|\bcr\.?p\.?c\b", "Bharatiya Nagarik Suraksha Sanhita, 2023", "1 July 2024"),
]


def repealed_info(act_text: str):
    t = act_text.lower()
    for pat, new, since in REPEALED:
        if re.search(pat, t):
            return new, since
    return None

TOKEN_KB = re.compile(r"\[KB:([a-z0-9_]+)\]")
TOKEN_LAW = re.compile(r"\[LAW:([^\]|]+?)(?:\|\s*([^\]]+?))?\]")
SECTION_RAW = re.compile(r"(?i)(?<![\w\[|])(?:section|sec\.|s\.|u/s|धारा|dhara)\s*(\d+[A-Za-z]?)(?:\(\w+\))*"
                         r"(?:\s+(?:of\s+(?:the\s+)?)?(?-i:(Code on (?:Wages|Social Security)(?:,?\s*\d{4})?|[A-Z][A-Za-z.]+(?:\s+(?:[A-Z][A-Za-z()]+|of|and|the|for|from|with|on|in|to))"
                         r"{0,8}?\s+(?:Act|Code|Sanhita|Adhiniyam)(?:,?\s*\d{4})?|IPC|CrPC|BNSS|BNS|BSA|NI Act))\b)?")
_W = r"(?:[A-Z(][\w()&'.-]*|of|and|the|for|from|with|on|in|to)"
ACT_RAW = re.compile(r"([A-Z(][\w()&'.-]*(?:\s+" + _W + r"){0,14}\s+(?:Act|Code|Rules|Sanhita|Adhiniyam|Scheme))(?:,|\s+of)?\s*(\d{4})")
CASE_LAW = [
    re.compile(r"\b[A-Z][\w.&']+(?:\s+[A-Z][\w.&']+){0,6}\s+(?:v\.|vs\.?|versus)\s+[A-Z][\w.&']+(?:\s+[A-Z][\w.&']+){0,6}"),
    re.compile(r"\bAIR\s*\d{4}\b"),
    re.compile(r"\(?\d{4}\)?\s*\d+\s*SCC\s*\d+"),
    re.compile(r"\b\d{4}\s+INSC\s+\d+"),
]
FILLER = re.compile(r"((?:(?:Also|also|The|the|Under|under|See|As per|Per|And|In|By|As)\s+)*)")
WARN_CASE = "❌ *[court-case citation removed — AI cannot verify judgments]*"
INDIACODE = "https://www.indiacode.nic.in"


def _kb_match(act: str, section: str | None) -> str | None:
    """If an AI-recalled citation is actually in the KB, upgrade it to verified."""
    na = kb._norm(act)
    sec = re.sub(r"[^0-9a-z]", "", (section or "").lower())
    for e in kb.load().values():
        if kb._norm(e["act"]) == na or (len(na) > 10 and (kb._norm(e["act"]).startswith(na) or na.startswith(kb._norm(e["act"])))):
            esec = re.sub(r"[^0-9a-z]", "", str(e.get("section", "")).lower())
            if not sec or (esec and (esec == sec or sec.startswith(esec))):
                return e["id"]
    return None


def _render_kb(e: dict, links: bool) -> str:
    sec = str(e.get("section"))
    if e["act"].startswith("General"):
        label = e["title"]
    elif sec in ("none", "process", "status", "model"):
        label = e["act"]
    else:
        label = f"{e['act']} — {'s. ' + sec if not sec.lower().startswith('rule') else sec}"
    return f"✅ [{label}]({e['source_url']})" if links else f"{label}"


def _render_ai(act: str, section: str | None, links: bool) -> str:
    label = f"{act.strip()}{', ' + section.strip() if section else ''}"
    return f"⚠️ *{label}* ([verify]({INDIACODE}))" if links else f"[[VERIFY: {label}]]"


def _render_repealed(act: str, section: str | None, new: str, since: str, links: bool) -> str:
    old = f"{act.strip()}{' ' + section.strip() if section else ''}"
    return (f"🔄 *{old}* → replaced by **{new}** (from {since})" if links
            else f"[[CHECK: {old} was replaced by {new} from {since}]]")


def check_and_render(text: str, markdown_links: bool = True) -> tuple[str, dict]:
    rep = {"verified": [], "ai_recalled": [], "repealed": [], "case_law_removed": [], "unknown_kb_ids": []}
    if not text:
        rep["clean"] = True
        return text, rep
    kbmap = kb.load()
    protected = []  # rendered citations we must not re-scan

    def protect(s: str) -> str:
        protected.append(s)
        return f"\x00{len(protected) - 1}\x00"

    # 1. Case law: remove (with its sentence)
    for pat in CASE_LAW:
        while (m := pat.search(text)):
            start = max(text.rfind(". ", 0, m.start()), text.rfind("।", 0, m.start()), text.rfind("\n", 0, m.start()))
            start = 0 if start == -1 else start + 1
            ends = [i for i in (text.find(". ", m.end()), text.find("।", m.end()), text.find("\n", m.end())) if i != -1]
            end = min(ends) + 1 if ends else len(text)
            rep["case_law_removed"].append(text[start:end].strip())
            text = text[:start] + " " + protect(WARN_CASE) + text[end:]

    # 2. Verified KB tokens
    def _kb(m):
        i = m.group(1)
        if i not in kbmap:
            rep["unknown_kb_ids"].append(i)
            return ""
        if i not in rep["verified"]:
            rep["verified"].append(i)
        return protect(_render_kb(kbmap[i], markdown_links))
    text = TOKEN_KB.sub(_kb, text)

    # 3. AI-recalled LAW tokens
    def _law(m):
        act, sec = m.group(1).strip(), (m.group(2) or "").strip() or None
        return protect(_classify(act, sec, rep, markdown_links, kbmap))
    text = TOKEN_LAW.sub(_law, text)

    # 4. Untagged mentions in prose
    def _sec_raw(m):
        sec, act = m.group(1), (m.group(2) or "").strip()
        if not act:
            return m.group(0)  # bare "section 17" — context unknown; left as is (counted nowhere)
        return protect(_classify(act, f"s. {sec}", rep, markdown_links, kbmap))
    text = SECTION_RAW.sub(_sec_raw, text)

    # Exact names of KB laws mentioned in prose are real -> keep as plain text, don't re-scan
    for name in sorted({e["act"] for e in kbmap.values() if not e["act"].startswith("General")}, key=len, reverse=True):
        if name in text:
            text = text.replace(name, protect(name))

    def _act_raw(m):
        pm = FILLER.match(m.group(1))
        prefix, name = pm.group(1), m.group(1)[pm.end():]
        return prefix + protect(_classify(f"{name.strip()}, {m.group(2)}", None, rep, markdown_links, kbmap, raw=m.group(0)[len(prefix):]))
    text = ACT_RAW.sub(_act_raw, text)

    for i, s in enumerate(protected):
        text = text.replace(f"\x00{i}\x00", s)
    text = re.sub(r"[ \t]{2,}", " ", text)
    rep["clean"] = not (rep["ai_recalled"] or rep["repealed"] or rep["case_law_removed"] or rep["unknown_kb_ids"])
    return text, rep


def _classify(act, sec, rep, links, kbmap, raw=None) -> str:
    rp = repealed_info(act)
    if rp:
        rep["repealed"].append(f"{act} {sec or ''}".strip())
        return _render_repealed(act, sec, rp[0], rp[1], links)
    kid = _kb_match(act, re.sub(r"(?i)^s(ection)?\.?\s*", "", sec or "") or None)
    if kid:
        if kid not in rep["verified"]:
            rep["verified"].append(kid)
        return _render_kb(kbmap[kid], links) if (sec or raw is None) else (raw if not links else _render_kb(kbmap[kid], links))
    rep["ai_recalled"].append(f"{act} {sec or ''}".strip())
    return _render_ai(act, sec, links)


def merge(reports: list[dict]) -> dict:
    keys = ["verified", "ai_recalled", "repealed", "case_law_removed", "unknown_kb_ids"]
    out = {k: [] for k in keys}
    for r in reports:
        for k in keys:
            for v in r.get(k, []):
                if v not in out[k]:
                    out[k].append(v)
    out["clean"] = not (out["ai_recalled"] or out["repealed"] or out["case_law_removed"] or out["unknown_kb_ids"])
    return out


def guard_obj(obj, reports: list, markdown_links: bool = True):
    if isinstance(obj, str):
        t, r = check_and_render(obj, markdown_links)
        reports.append(r)
        return t
    if isinstance(obj, list):
        return [guard_obj(x, reports, markdown_links) for x in obj]
    if isinstance(obj, dict):
        return {k: guard_obj(v, reports, markdown_links) for k, v in obj.items()}
    return obj
