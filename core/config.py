"""All settings in one place. Values come from environment variables / .env (local) or Streamlit secrets (cloud).

    GROQ_API_KEY        required — https://console.groq.com/keys
    GROQ_MODEL          main model for opinions and drafts      (default openai/gpt-oss-120b)
    GROQ_FAST_MODEL     model for intake, follow-ups, practice  (default openai/gpt-oss-20b — separate free-tier quota)
    GROQ_STT_MODEL      speech-to-text                          (default whisper-large-v3-turbo)
    SQLITE_PATH         chats + documents database              (default data/lawyaar.db)
Swapping the model = changing GROQ_MODEL / GROQ_FAST_MODEL. Nothing else in the code names a model.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HIGH_VALUE_INR = 500_000            # above this, strongly recommend a lawyer
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"   # local, free, English + Hindi
EXPORTED = ["GROQ_API_KEY", "GROQ_MODEL", "GROQ_FAST_MODEL", "GROQ_STT_MODEL", "SQLITE_PATH"]


def _load_dotenv():
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.split(" #")[0].strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _load_streamlit_secrets():
    """LangChain/Groq read os.environ, so copy Streamlit Cloud secrets there once."""
    try:
        import streamlit as st
        for k in EXPORTED:
            if k in st.secrets and not os.getenv(k):
                os.environ[k] = str(st.secrets[k])
    except Exception:
        pass


_load_dotenv()
_load_streamlit_secrets()


def get(key: str, default=None):
    return os.getenv(key) or default


MODEL = get("GROQ_MODEL", "openai/gpt-oss-120b")
FAST_MODEL = get("GROQ_FAST_MODEL", "openai/gpt-oss-20b")
STT_MODEL = get("GROQ_STT_MODEL", "whisper-large-v3-turbo")
DB_PATH = get("SQLITE_PATH", str(ROOT / "data" / "lawyaar.db"))


def model_label() -> str:
    return f"groq:{MODEL} (+{FAST_MODEL})"
