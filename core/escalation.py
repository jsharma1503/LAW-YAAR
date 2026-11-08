"""Safety rules — plain code that runs BEFORE any model call, so a model mistake can't skip them.

Levels (highest wins):
  crisis       user may be at risk                                  -> helplines only, no legal answer, no model call
  refer        outside the 4 problems or too risky for an AI         -> fixed referral to free legal aid, no model call
               (case/FIR/arrest against the user, court summons, cheque bounce, family matters, violence, land, cyber fraud)
  refuse_part  user wants to threaten/harass/defame or asks for made-up law -> that part is declined, lawful help continues
  caution      in scope but high stakes (large amount, threats, a deadline)  -> help + "have a lawyer check this" banner
  none
The model's intake can also raise flags; it can raise the level but never lower it.
"""
import re

from core import config

ORDER = ["none", "caution", "refuse_part", "refer", "crisis"]
D = r"[ऀ-ॿ]"  # Devanagari letter — Hindi keywords need word boundaries ("वारंटी" warranty contains "वारंट" warrant)

RULES = [
    ("crisis", "self_harm", r"suicid|kill myself|end my life|आत्महत्या|खुदकुशी|khudkushi|jaan de d[ue]ng[ai]|marna chaht[ai]|jeene ka mann nahi"),
    ("refer", "case_against_user",
     r"arrest|giraftar|गिरफ्तार|\bjail\b|"
     r"(\bfir\b|case|complaint|एफआईआर|केस|मुकदमा).{0,30}(against me|on me|mere (upar|khilaf)|mujh ?par|मेरे (ऊपर|खिलाफ)|मुझ पर)|"
     r"(against me|mere (upar|khilaf)|mujh ?par|मेरे (ऊपर|खिलाफ)|मुझ पर).{0,30}(\bfir\b|case|complaint|एफआईआर|केस|मुकदमा)|"
     r"police.{0,25}(called me|summoned|bulaya|aane ko)|पुलिस.{0,20}(बुलाया|फ़ोन|फोन)"),
    ("refer", "court_papers", rf"summons|(?<!{D})समन(?!{D})|\bwarrant\b|(?<!{D})वारंट(?!{D})|court (date|hearing)|next hearing|अदालत (का|से) नोटिस"),
    ("refer", "cheque_bounce", r"cheque (bounce|dishono)|check bounce|चेक बाउंस"),
    ("refer", "family", r"divorce|talaq|तलाक|custody|dowry|दहेज|domestic violence|घरेलू हिंसा|alimony"),
    ("refer", "violence", r"\bassault|\brape\b|molest|sexual harass|यौन|मारपीट|maar ?pit|beats? me|hits? me|slaps? me|attack(s|ed) me"),
    ("refer", "property_title", r"inheritance|succession|wasiyat|वसीयत|\bwill deed|land dispute|zameen|ज़मीन|जमीन|bantwara|बंटवारा|property title|mutation"),
    ("refer", "cyber_fraud", r"\botp\b|hacked|upi fraud|scam call|phishing|साइबर|cyber ?fraud"),
    ("refuse_part", "harm_intent",
     r"sabak sikha|सबक सिखा|teach (him|her|them) a lesson|beat (him|her|them) up|threaten (him|her|them)|scare (him|her|them)|"
     r"viral kar|make .{0,25}viral|spread .{0,20}(photo|video)|वायरल कर|post (his|her|their) (photo|number|address)|badnaam|बदनाम|defame|"
     r"goons?|gunde|गुंडे|log bhej|लोग भेज|tod ?fod|तोड़\s?फोड़|damage (his|her) (car|house|property)"),
    ("refuse_part", "fabrication",
     r"make up (a |some )?(section|law|judg)|invent (a |some )?(section|law)|fake (section|law|bill|receipt|document|judg)|"
     r"nakli|नकली|forge|koi bhi section likh|कोई भी धारा लिख|section bana|धारा बना|chahe exist na kare"),
    ("caution", "being_threatened", r"dhamki|धमकी|threaten(ed|ing) me|threat to me|harass(ed|ing) me"),
    ("caution", "deadline", r"reply within|within \d+ days|last date|deadline|अंतिम तिथि|notice (mila|aaya|received)|नोटिस (मिला|आया)"),
]
CASE_LAW_REQUEST = re.compile(r"case ?law|judg(e)?ment|precedent|supreme court|high court|citation|फैसल|नज़ीर|नजीर", re.I)
_AMOUNT = re.compile(r"(?:₹|rs\.?|inr|rupees?|रुपये|रुपए)?\s*(\d[\d,]*(?:\.\d+)?)\s*"
                     r"(lakh|lac|लाख|crore|cr\b|करोड़|k\b|thousand|hazaar|hazar|हज़ार|हजार)?", re.I)
LLM_FLAGS = {"case_against_user": "refer", "court_papers": "refer", "out_of_scope": "refer", "self_harm": "crisis",
             "harm_intent": "refuse_part", "fabrication_request": "refuse_part", "threat_to_user": "caution",
             "deadline": "caution", "high_value": "caution"}


def amounts_in(text: str) -> list[int]:
    out = []
    for m in _AMOUNT.finditer(text):
        n, unit = float(m.group(1).replace(",", "") or 0), (m.group(2) or "").lower()
        mult = {"lakh": 1e5, "lac": 1e5, "लाख": 1e5, "crore": 1e7, "cr": 1e7, "करोड़": 1e7,
                "k": 1e3, "thousand": 1e3, "hazaar": 1e3, "hazar": 1e3, "हज़ार": 1e3, "हजार": 1e3}.get(unit)
        if mult:
            n *= mult
        elif n < 1000 and not re.search(r"₹|rs|inr|rupee|रुप", m.group(0), re.I):
            continue                      # small bare numbers are dates/counts
        elif 1900 <= n <= 2100:
            continue                      # a year
        out.append(int(n))
    return out


def check(text: str, llm_flags: list | None = None, llm_amount: float | None = None) -> dict:
    level, reasons = "none", []

    def bump(lv, why):
        nonlocal level
        if why not in reasons:
            reasons.append(why)
        if ORDER.index(lv) > ORDER.index(level):
            level = lv

    for lv, why, pat in RULES:
        if re.search(pat, text, re.I):
            bump(lv, why)
    amts = amounts_in(text) + ([int(llm_amount)] if llm_amount else [])
    if amts and max(amts) > config.HIGH_VALUE_INR:
        bump("caution", "high_value")
    for f in llm_flags or []:
        if f in LLM_FLAGS:
            bump(LLM_FLAGS[f], f)
    return {"level": level, "reasons": reasons, "max_amount": max(amts) if amts else None,
            "case_law_requested": bool(CASE_LAW_REQUEST.search(text))}
