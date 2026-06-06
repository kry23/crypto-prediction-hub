"""Architecture page — a Graphviz diagram of the live system.

Static reference: how a request flows (browser -> Cloudflare -> tunnel -> nginx
-> Streamlit -> PG) and how the prediction pipeline (scheduler -> SQLite ->
sync bridge -> PG) is wired. Rendered with st.graphviz_chart (DOT string, no
extra dependency).
"""
from __future__ import annotations

import streamlit as st

from crypto_predictor.ui.auth import require_auth

require_auth()
st.title("🗺 Architecture")
st.caption("Live system on the Hostinger VPS — krypredictor.com")

_DOT = r"""
digraph architecture {
  rankdir=TB;
  bgcolor="transparent";
  node [shape=box, style="rounded,filled", fontname="IBM Plex Sans",
        color="#2b3650", fillcolor="#161D2E", fontcolor="#E6EDF3", penwidth=1.3];
  edge [color="#8B98AD", fontname="IBM Plex Mono", fontsize=10, fontcolor="#8B98AD"];

  browser  [label="Browser (you)", fillcolor="#1B2438"];
  cf       [label="Cloudflare\nTLS + Tunnel edge", fillcolor="#1B2438"];
  tg       [label="Telegram bot\nheartbeat + digests", fillcolor="#1B2438"];
  ext      [label="OKX · NewsAPI · CoinGecko", fillcolor="#1B2438"];

  subgraph cluster_vps {
    label="Hostinger VPS — Ubuntu 24.04";
    style="rounded"; color="#2DD4BF"; fontcolor="#2DD4BF"; fontname="IBM Plex Sans";

    cfd     [label="cloudflared\ntunnel connector"];
    nginx   [label="nginx :80\nbasic-auth gate"];
    ui      [label="Streamlit UI :8501\nDashboard · Track Record · Journal\nArchitecture · Operator · Ask Claude"];
    sched   [label="scheduler (systemd)\n06:00 predict · 06:30 validate\n+ ingest · backup · recalibrate"];
    intel   [label="intel-bridge (systemd)\nwhale + news poller"];
    sync    [label="sync timer — every 10 min\nSQLite -> PG (upsert)",
             fillcolor="#10241d", color="#2DD4BF", fontcolor="#9af2e3"];
    backup  [label="backup timer — 07:00 UTC\npg_dump + sqlite + parquet"];

    sqlite  [label="SQLite\npredictions.db + caches\nPIPELINE SOURCE OF TRUTH",
             shape=cylinder, fillcolor="#2a1f10", color="#F5A623", fontcolor="#f6c87a"];
    pg      [label="PostgreSQL 16\nUI mirror + mart tables",
             shape=cylinder, fillcolor="#10241d", color="#2DD4BF", fontcolor="#9af2e3"];
    parquet [label="parquet history\ndata/history", shape=folder, fillcolor="#1B2438"];
    backups [label="/var/lib/.../backups\n14-day retention", shape=folder, fillcolor="#1B2438"];
  }

  // request path
  browser -> cf -> cfd -> nginx -> ui;
  ui -> pg [label="reads"];

  // prediction pipeline (SQLite is the source of truth)
  ext -> sched [label="fetch", style=dotted, dir=back];
  sched -> sqlite [label="writes"];
  sched -> parquet [label="ingest"];
  sched -> tg [label="push"];

  // the interim bridge + intel
  sqlite -> sync [style=dashed, color="#2DD4BF"];
  sync -> pg [label="mirror", style=dashed, color="#2DD4BF"];
  intel -> pg;

  // backups
  sqlite -> backup [style=dotted, dir=back];
  pg -> backup [style=dotted, dir=back];
  backup -> backups;
}
"""

st.graphviz_chart(_DOT, use_container_width=True)

st.markdown(
    """
**How to read it**

- **Request path** (solid): `Browser → Cloudflare (TLS + Tunnel) → cloudflared → nginx (basic-auth) → Streamlit`. The UI **reads PostgreSQL**.
- **Pipeline**: the **scheduler** writes the **SQLite** DBs — the pipeline's *source of truth* (amber) — plus the parquet history, and pushes Telegram alerts.
- **The bridge** (teal, dashed): a 10-min timer mirrors SQLite → PostgreSQL so the UI sees fresh data. This is the **v1.0 interim**; converting the pipeline to PG-native (retiring the bridge) is the planned **v1.1**.
- **Backups** (dotted): nightly `pg_dump` + SQLite + parquet to a 14-day local store.
"""
)
