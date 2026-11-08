"""Static HTML/CSS for the app chrome. Palette: cream · ink black · burnt orange. All copy is original.
Colors that Streamlit draws itself (sidebar, buttons, links) are set in .streamlit/config.toml; this CSS refines the rest."""

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Inter:wght@400;500;600&display=swap');
:root { --ink:#141210; --ink2:#221E1A; --gold:#CC5500; --gold-d:#A64400; --gold-l:#F08A4B; --gold-soft:#FBE7D8;
        --white:#FFFBF2; --cream:#F5EFE0; --mute:#6B6257; --line:#E4D9C3; }
html, body, .stMarkdown, p, li, button, input, textarea, label { font-family: 'Inter', sans-serif; }
h1, h2, h3, h4, .ns-serif { font-family: 'Playfair Display', Georgia, serif !important; color: var(--ink); letter-spacing: -0.01em; }
#MainMenu, footer, [data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"] { background: var(--cream); border-bottom: 2px solid var(--gold); }
.block-container { max-width: 980px; padding-top: 4.2rem; padding-bottom: 8rem; }

/* ---------- buttons: black, gold on hover; primary = gold with black text (readable contrast) */
.stButton button, .stDownloadButton button, .stFormSubmitButton button {
  border-radius: 10px; min-height: 42px; font-weight: 500; border: 1px solid var(--line); background: var(--white); color: var(--ink); }
.stButton button:hover, .stDownloadButton button:hover { border-color: var(--gold); color: var(--gold-d); }
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {
  background: var(--gold); border: 1px solid var(--gold); color: #FFF8EC !important; font-weight: 600; }
.stButton button[kind="primary"]:hover { background: var(--ink); border-color: var(--ink); color: var(--gold-l) !important; }

/* ---------- home: simple welcome */
.ns-welcome { text-align: center; margin: 6vh auto 26px; max-width: 640px; }
.ns-mark { width: 64px; height: 64px; border-radius: 18px; background: var(--ink); color: var(--gold-l); display: inline-flex;
  align-items: center; justify-content: center; font-size: 30px; box-shadow: 0 10px 30px rgba(204,85,0,.25); }
.ns-welcome h1 { font-size: 2.35rem; margin: 18px 0 8px; }
.ns-welcome h1 em { font-style: normal; color: var(--gold-d); }
.ns-welcome p { color: var(--mute); font-size: 1.02rem; margin: 0; }
[class*="st-key-sugg"] button { justify-content: flex-start; text-align: left; min-height: 56px; border-radius: 14px;
  background: var(--white); border: 1px solid var(--line); box-shadow: 0 1px 2px rgba(0,0,0,.03); }
[class*="st-key-sugg"] button:hover { background: var(--gold-soft); border-color: var(--gold); color: var(--ink); }
.ns-wfoot { text-align: center; color: var(--mute); font-size: .82rem; margin-top: 18px; }
.ns-wfoot b { color: var(--ink); }

/* ---------- chat */
[data-testid="stChatMessage"] { background: var(--white); border: 1px solid var(--line); border-radius: 16px; padding: 14px 18px; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { flex-direction: row-reverse; background: var(--ink);
  border-color: var(--ink); margin-left: 14%; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) * { color: #F5EFE0 !important; }
[data-testid="stChatMessageAvatarUser"] { background: var(--gold) !important; }
[data-testid="stChatMessage"] h4 { font-size: 1.05rem; margin-top: .9rem; border-left: 3px solid var(--gold); padding-left: 8px; }
[data-testid="stChatMessage"] a { color: var(--gold-d); }
[data-testid="stChatInput"] { border-radius: 16px; border: 1.5px solid var(--ink) !important; }
[data-testid="stChatInput"]:focus-within { border-color: var(--gold) !important; box-shadow: 0 0 0 3px rgba(204,85,0,.18); }
[data-testid="stBottomBlockContainer"] { background: linear-gradient(180deg, rgba(245,239,224,0) 0%, var(--cream) 35%); }
.stTabs [aria-selected="true"] { color: var(--ink) !important; }
.stTabs [data-baseweb="tab-highlight"] { background: var(--gold) !important; }

/* ---------- sidebar (colors from config.toml [theme.sidebar]) */
[data-testid="stSidebar"] .stButton button { width: 100%; justify-content: flex-start; text-align: left; border: none;
  background: transparent; color: #EFE6D4; font-size: .88rem; min-height: 36px; }
[data-testid="stSidebar"] .stButton button:hover { background: #2A241E; color: var(--gold-l); }
[data-testid="stSidebar"] .stButton button[kind="primary"] { background: var(--gold); color: #FFF8EC !important; justify-content: center; }
.ns-side-label { font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; color: var(--gold) !important; font-weight: 700; margin: 16px 0 4px; }
.ns-small { font-size: .75rem; color: #A89C8A !important; line-height: 1.5; }

@media (max-width: 800px) { .ns-welcome h1 { font-size: 1.9rem; }
  [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { margin-left: 4%; } }
</style>
"""

BRAND = "LAW-YAAR"                     # change the product name here (also assets/logo.svg)
TAGLINE = "Your legal yaar."

WELCOME = """<div class="ns-welcome"><div class="ns-mark">⚖</div>
<h1>Tell me what <em>happened.</em></h1>
<p>Deposit not returned · refund not received · salary withheld · a notice you received.<br>
Type, tap 🎤 to speak, or 📎 attach a PDF — in English, हिन्दी or Hinglish. I'll ask a few questions first, like a lawyer would.</p></div>"""

SUGGESTIONS = [
    ("🏠 PG owner cut my deposit for 'painting'", "Bengaluru mein PG owner ne mere 30,000 deposit mein se 18,000 painting aur cleaning ke naam pe kaat liye. Maine 15 September 2026 ko room khaali kiya, 11 mahine raha. Unhone koi bill nahi dikhaya."),
    ("🛒 AC broke down inside the warranty", "I bought a split AC for Rs 42,500 from a showroom in Kolkata on 10 May 2026. It stopped cooling in July. The service centre came three times and now says the compressor is not covered."),
    ("💼 Two months' salary not paid", "मेरे स्कूल ने अगस्त और सितंबर 2026 की सैलरी नहीं दी है, कुल 56,000 रुपये। मैं इंदौर में एक प्राइवेट स्कूल में टीचर हूँ। प्रिंसिपल हर बार कहते हैं अगले महीने।"),
    ("📨 Notice to repay my joining bonus", "My old employer in Hyderabad sent me a legal notice asking me to repay a Rs 1,00,000 joining bonus because I left after 8 months. The offer letter says the bonus is repayable if I leave within 12 months. What should I do?"),
]

WELCOME_FOOT = """<div class="ns-wfoot">Legal information, not legal advice · Free legal aid: <b>NALSA 15100</b> · Emergency <b>112</b></div>"""
