"""Global look-and-feel for the Streamlit console — injected once from app.py.

Mirrors the React console's "After-Hours Terminal" palette so both UIs feel like one
product: near-black canvas, amber accent, tabular-mono numerics, carded metrics.
"""
import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap');

:root {
  --bg:#0B0E13; --surface:#121722; --surface2:#1A2130; --border:#232C3B;
  --text:#E6EDF3; --muted:#9AA7B8; --accent:#F5B301;
  --bull:#22C55E; --bear:#F0556B;
}

html, body, [class*="css"], .stApp { font-family:'IBM Plex Sans', system-ui, sans-serif; }
h1, h2, h3 { font-family:'Space Grotesk', sans-serif !important; letter-spacing:-0.01em; }

/* Hide default Streamlit chrome for a cleaner shell */
#MainMenu, footer, header [data-testid="stToolbar"] { visibility:hidden; }
.block-container { padding-top:1.2rem; padding-bottom:2rem; max-width:1400px; }

/* Numbers read as instruments: tabular monospace on every metric value */
[data-testid="stMetricValue"], [data-testid="stMetricDelta"] {
  font-family:'IBM Plex Mono', monospace !important;
  font-variant-numeric:tabular-nums;
}

/* Metrics become carded panels */
[data-testid="stMetric"] {
  background:var(--surface); border:1px solid var(--border);
  border-radius:10px; padding:14px 16px;
}
[data-testid="stMetricLabel"] { color:var(--muted) !important; text-transform:uppercase;
  font-size:0.7rem !important; letter-spacing:0.5px; font-weight:600; }

/* Sidebar = navigation rail */
[data-testid="stSidebar"] { background:var(--surface); border-right:1px solid var(--border); }
[data-testid="stSidebar"] .stRadio > label { display:none; }            /* hide radio's own label */
[data-testid="stSidebar"] [role="radiogroup"] > label {
  display:flex; align-items:center; gap:.5rem; width:100%;
  padding:.5rem .7rem; margin:1px 0; border-radius:8px;
  color:var(--muted); cursor:pointer; transition:background .15s, color .15s;
}
[data-testid="stSidebar"] [role="radiogroup"] > label:hover { background:var(--surface2); color:var(--text); }
[data-testid="stSidebar"] [role="radiogroup"] input:checked + div { color:var(--accent); }
[data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) {
  background:var(--surface2); color:var(--text); font-weight:600;
}
[data-testid="stSidebar"] [role="radiogroup"] > label > div:first-child { display:none; } /* hide radio dot */

/* Buttons */
.stButton > button {
  border:1px solid var(--border); border-radius:8px; font-weight:500;
  transition:background .15s, border-color .15s;
}
.stButton > button:hover { border-color:var(--accent); }
.stButton > button[kind="primary"] {
  background:var(--accent); color:#0B0E13; border:none; font-weight:600;
}

/* Tabs (some pages still use inner tabs) */
.stTabs [data-baseweb="tab-list"] { gap:2px; border-bottom:1px solid var(--border); }
.stTabs [data-baseweb="tab"] { border-radius:8px 8px 0 0; }

/* Dataframes + inputs */
[data-testid="stDataFrame"] { border:1px solid var(--border); border-radius:8px; }
.stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div {
  border-radius:8px !important;
}

/* Tighten expanders */
.streamlit-expanderHeader { font-weight:600; }
</style>
"""


def inject() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def topbar(name: str, regime: dict | None, ready: bool | None) -> None:
    """Slim header: page title + live regime + API health."""
    us = (regime or {}).get("us") or {}
    ind = (regime or {}).get("india") or {}
    reg = ""
    if us or ind:
        reg = (f"<span style='color:var(--muted)'>US</span> "
               f"<b style='color:var(--text)'>{(us.get('regime') or '—').replace('_','-')}</b> · "
               f"<span style='color:var(--muted)'>IN</span> "
               f"<b style='color:var(--text)'>{(ind.get('regime') or '—').replace('_','-')}</b>")
    dot_color = "#22C55E" if ready else "#F0556B" if ready is False else "#9AA7B8"
    health = f"<span style='color:{dot_color}'>● {'API ok' if ready else 'API down' if ready is False else '…'}</span>"
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;justify-content:space-between;
             border-bottom:1px solid var(--border);padding:0 0 .7rem 0;margin-bottom:1rem">
          <div style="font-family:'Space Grotesk';font-weight:700;font-size:1.15rem">{name}</div>
          <div style="display:flex;gap:1.5rem;font-size:.85rem">{reg}{health}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
