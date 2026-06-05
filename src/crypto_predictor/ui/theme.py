"""Midnight Desk theme — injected CSS for the Streamlit UI.

A refined dark "trading-desk" look that pairs with the palette in
``.streamlit/config.toml``:

- IBM Plex Sans for text, IBM Plex Mono for figures (tabular numerals so
  columns of numbers line up — essential for a data dashboard).
- Teal accent on a slate-navy ground; a faint top glow for depth.
- Metric cards lifted onto panels with a teal edge.

``inject_theme()`` is called once at the top of ``app.py``'s ``main()``; because
Streamlit re-runs the script top-to-bottom on every interaction, the CSS is
re-emitted each run and stays applied across all pages.
"""
from __future__ import annotations

import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --mw-bg: #0D1220;
  --mw-panel: #161D2E;
  --mw-teal: #2DD4BF;
  --mw-teal-dim: rgba(45, 212, 191, 0.14);
  --mw-text: #E6EDF3;
  --mw-muted: #8B98AD;
  --mw-border: rgba(139, 152, 173, 0.16);
}

/* Atmosphere: a faint teal glow up top so the ground reads as depth, not a slab. */
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1100px 380px at 50% -140px, rgba(45, 212, 191, 0.07), transparent 70%),
    var(--mw-bg);
}

/* Figures in mono with tabular + slashed-zero so numbers align and read cleanly. */
[data-testid="stMetricValue"],
[data-testid="stMetricDelta"],
.stDataFrame [role="grid"],
code, pre, kbd {
  font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, monospace !important;
  font-feature-settings: 'tnum' 1, 'zero' 1;
}

/* Headings: a hair tighter, with weight and a cool tone. */
h1, h2, h3, h4 {
  font-weight: 600;
  letter-spacing: -0.012em;
  color: var(--mw-text);
}

/* Metric cards: lift onto a panel with a teal edge and a soft drop. */
[data-testid="stMetric"] {
  background: var(--mw-panel);
  border: 1px solid var(--mw-border);
  border-left: 3px solid var(--mw-teal);
  border-radius: 10px;
  padding: 14px 16px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28);
}
[data-testid="stMetricLabel"] {
  color: var(--mw-muted);
  text-transform: uppercase;
  font-size: 0.72rem;
  letter-spacing: 0.08em;
}
[data-testid="stMetricValue"] { color: var(--mw-text); font-weight: 600; }

/* Top nav + header: let the glow show through. */
[data-testid="stHeader"] { background: transparent; }

/* Sidebar / panels. */
[data-testid="stSidebar"] {
  background: var(--mw-panel);
  border-right: 1px solid var(--mw-border);
}

/* Dataframes: contain them in a bordered panel. */
.stDataFrame, [data-testid="stDataFrame"] {
  border: 1px solid var(--mw-border);
  border-radius: 10px;
  overflow: hidden;
}

/* Buttons: quiet by default, teal on hover. */
.stButton > button, .stDownloadButton > button {
  border-radius: 8px;
  border: 1px solid var(--mw-border);
  font-weight: 500;
  transition: border-color 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  border-color: var(--mw-teal);
  color: var(--mw-teal);
  box-shadow: 0 0 0 3px var(--mw-teal-dim);
}

/* Selected tab + links in teal; inline code as teal chips. */
.stTabs [aria-selected="true"] { color: var(--mw-teal) !important; }
a, a:visited { color: var(--mw-teal); }
code {
  color: var(--mw-teal);
  background: var(--mw-teal-dim);
  padding: 1px 5px;
  border-radius: 4px;
}

/* Faint dividers. */
hr { border-color: var(--mw-border) !important; }
</style>
"""


def inject_theme() -> None:
    """Emit the Midnight Desk CSS into the page (call once per run, early)."""
    st.markdown(_CSS, unsafe_allow_html=True)
