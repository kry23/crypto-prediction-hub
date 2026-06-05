"""AG-Grid tables themed to match Midnight Desk.

Streamlit's native ``st.dataframe`` is a canvas grid — CSS can't touch it, so it
stays light/grey no matter the theme. This wraps ``streamlit-aggrid`` (a real
DOM grid) with the slate-navy + teal palette and IBM Plex Mono figures, plus
optional sign colouring (green ↑ / red ↓) for signed numeric columns.

Use :func:`render_table` everywhere we previously called ``st.dataframe``.
"""
from __future__ import annotations

from typing import Iterable, Sequence

import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

# AG-Grid is themed via CSS custom properties; override them on the theme class
# to repaint the (light) "alpine" theme into Midnight Desk dark.
_AG_DARK_CSS: dict[str, dict[str, str]] = {
    ".ag-theme-alpine": {
        "--ag-background-color": "#161D2E",
        "--ag-odd-row-background-color": "#131A28",
        "--ag-header-background-color": "#1B2438",
        "--ag-foreground-color": "#E6EDF3",
        "--ag-header-foreground-color": "#8B98AD",
        "--ag-border-color": "rgba(139, 152, 173, 0.18)",
        "--ag-row-border-color": "rgba(139, 152, 173, 0.10)",
        "--ag-row-hover-color": "rgba(45, 212, 191, 0.10)",
        "--ag-selected-row-background-color": "rgba(45, 212, 191, 0.16)",
        "--ag-range-selection-border-color": "#2DD4BF",
        "--ag-font-family": "'IBM Plex Mono', ui-monospace, monospace",
        "--ag-font-size": "13px",
        "--ag-header-column-separator-display": "none",
    },
    ".ag-root-wrapper": {
        "border": "1px solid rgba(139, 152, 173, 0.18)",
        "border-radius": "10px",
        "overflow": "hidden",
    },
    ".ag-header-cell-label": {
        "font-weight": "600",
        "letter-spacing": "0.04em",
        "text-transform": "uppercase",
        "font-size": "11px",
    },
}

# Colour a signed numeric cell: teal-green up, red down, muted at zero/blank.
_SIGN_COLOR = JsCode(
    """
    function(p) {
        if (p.value === null || p.value === undefined || p.value === '') return {};
        const v = parseFloat(p.value);
        if (isNaN(v)) return {};
        if (v > 0) return {'color': '#34D399', 'fontWeight': '600'};
        if (v < 0) return {'color': '#F87171', 'fontWeight': '600'};
        return {'color': '#8B98AD'};
    }
    """
)


def render_table(
    data: pd.DataFrame | list[dict],
    *,
    color_cols: Sequence[str] = (),
    key: str | None = None,
) -> None:
    """Render ``data`` as a Midnight-Desk AG-Grid (display-only).

    ``color_cols`` are signed numeric columns to colour by sign. ``key`` must be
    unique per grid on a page.
    """
    df = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    if df.empty:
        return

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(
        sortable=True, resizable=True, filter=False,
        suppressMenu=True, cellStyle={"fontFamily": "'IBM Plex Mono', monospace"},
    )
    for col in color_cols:
        if col in df.columns:
            gb.configure_column(col, cellStyle=_SIGN_COLOR)
    options = gb.build()
    options["domLayout"] = "autoHeight"   # size to content, no inner scrollbar

    AgGrid(
        df,
        gridOptions=options,
        theme="alpine",
        custom_css=_AG_DARK_CSS,
        allow_unsafe_jscode=True,
        fit_columns_on_grid_load=True,
        update_on=[],            # display only — no Streamlit reruns on sort
        key=key,
    )
