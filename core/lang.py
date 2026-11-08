"""Cheap, deterministic language detection: English / Hindi (Devanagari) / Hinglish (Hindi in Roman script)."""
import re

HINGLISH_MARKERS = {
    "hai", "hain", "nahi", "nahin", "nhi", "mera", "meri", "mere", "mujhe", "kya", "kar", "karna", "karo",
    "diya", "diye", "raha", "rahi", "rahe", "paisa", "paise", "wapas", "vapas", "bhai", "aur", "lekin",
    "toh", "bhi", "kuch", "abhi", "sab", "hum", "main", "hoon", "hu", "tha", "thi", "gaya", "gayi",
    "mahine", "mahina", "bol", "bola", "boli", "bolta", "kaise", "kyun", "kab", "jab", "tak", "ke", "ki",
    "ko", "se", "ne", "ho", "ab", "pe", "par", "wala", "wali", "malik", "makan", "chahiye", "sakta",
    "sakti", "dena", "lena", "de", "le", "baad", "pehle", "din", "saal", "rupaye", "rupay",
}
# Words common in English that are also in the marker set; ignore them for English detection.
AMBIGUOUS = {"main", "par", "de", "le", "ho", "toh", "hu", "ab", "pe", "tak", "se", "ne", "ki", "ko", "ke", "bhi"}

NAMES = {"en": "English", "hi": "Hindi", "hinglish": "Hinglish"}


def detect(text: str) -> str:
    letters = re.findall(r"[A-Za-zऀ-ॿ]", text)
    if not letters:
        return "en"
    deva = sum(1 for c in letters if "ऀ" <= c <= "ॿ")
    # Hindi if mostly Devanagari, OR the user wrote a real Hindi sentence around a pasted English document.
    if deva / len(letters) > 0.3 or deva >= 20:
        return "hi"
    words = re.findall(r"[a-zA-Z]+", text.lower())
    strong = sum(1 for w in words if w in HINGLISH_MARKERS and w not in AMBIGUOUS)
    weak = sum(1 for w in words if w in AMBIGUOUS)
    if strong >= 2 or (strong >= 1 and weak >= 3):
        return "hinglish"
    return "en"


def instruction(lang: str) -> str:
    return {
        "hi": "Write ALL user-facing text in simple Hindi (Devanagari script). Keep [KB:...] tokens, amounts and dates unchanged.",
        "hinglish": "Write ALL user-facing text in Hinglish: Hindi words in Roman (English) letters mixed with common English words, "
                    "the way people type on WhatsApp (e.g. 'Aapka deposit wapas milna chahiye'). Do NOT use Devanagari. Keep [KB:...] tokens unchanged.",
        "en": "Write ALL user-facing text in simple, plain English (class-8 reading level). Keep [KB:...] tokens unchanged.",
    }[lang]
