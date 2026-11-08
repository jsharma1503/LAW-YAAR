"""LAW-YAAR — entry point.   streamlit run app.py

One page: the consultation chat (no page menu).
`from core import config` first: it loads .env / Streamlit secrets into the environment before Groq starts.
"""
from pathlib import Path

import streamlit as st

from core import config, ui  # noqa: F401  (config must load first)

HERE = Path(__file__).resolve().parent

st.set_page_config(page_title=f"{ui.BRAND} · {ui.TAGLINE}", page_icon="⚖️", layout="wide",
                   initial_sidebar_state="expanded")
st.markdown(ui.CSS, unsafe_allow_html=True)
try:
    st.logo(str(HERE / "assets" / "logo.svg"), size="large", icon_image=str(HERE / "assets" / "icon.svg"))
except Exception:  # older Streamlit / image type not supported -> no logo, app still works
    pass

page = st.Page(HERE / "views" / "chat.py", title=ui.BRAND, icon="⚖️", default=True)
st.navigation([page], position="hidden").run()   # one page, so no menu and no page name in the header
