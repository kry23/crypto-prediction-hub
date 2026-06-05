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

# Repaint the (light) "alpine" theme into Midnight Desk dark. CSS *variables*
# alone proved unreliable in the bundled build, so we also set explicit
# background/colour on the concrete elements (header, rows, cells) with the
# theme-class prefix — that always wins over the bundled light theme.
_BG = "#161D2E"
_BG_ODD = "#131A28"
_HEADER_BG = "#1B2438"
_TEXT = "#E6EDF3"
_MUTED = "#8B98AD"
_BORDER = "rgba(139, 152, 173, 0.16)"
_HOVER = "rgba(45, 212, 191, 0.10)"

_AG_DARK_CSS: dict[str, dict[str, str]] = {
    # CSS-var layer (works on builds that honour it) ...
    ".ag-theme-alpine": {
        "--ag-background-color": _BG,
        "--ag-odd-row-background-color": _BG_ODD,
        "--ag-header-background-color": _HEADER_BG,
        "--ag-foreground-color": _TEXT,
        "--ag-header-foreground-color": _MUTED,
        "--ag-border-color": _BORDER,
        "--ag-row-hover-color": _HOVER,
        "--ag-font-family": "'IBM Plex Mono', ui-monospace, monospace",
        "--ag-font-size": "13px",
        "background-color": _BG,
    },
    # ... and an explicit-element layer that always wins.
    ".ag-theme-alpine .ag-root-wrapper": {
        "background-color": _BG, "color": _TEXT,
        "border": f"1px solid {_BORDER}", "border-radius": "10px",
    },
    ".ag-theme-alpine .ag-header": {
        "background-color": _HEADER_BG, "border-bottom": f"1px solid {_BORDER}",
    },
    ".ag-theme-alpine .ag-header-cell": {"color": _MUTED},
    ".ag-theme-alpine .ag-header-cell-label": {
        "font-weight": "600", "letter-spacing": "0.04em",
        "text-transform": "uppercase", "font-size": "11px", "color": _MUTED,
    },
    ".ag-theme-alpine .ag-row": {
        "background-color": _BG, "color": _TEXT,
        "border-bottom": f"1px solid rgba(139,152,173,0.08)",
    },
    ".ag-theme-alpine .ag-row-odd": {"background-color": _BG_ODD},
    ".ag-theme-alpine .ag-row-hover": {"background-color": _HOVER},
    ".ag-theme-alpine .ag-cell": {"color": _TEXT, "border": "none"},
    ".ag-theme-alpine .ag-paging-panel": {
        "background-color": _HEADER_BG, "color": _MUTED,
        "border-top": f"1px solid {_BORDER}",
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
        suppressMenu=True,                 # AG-Grid < 31
        suppressHeaderMenuButton=True,      # AG-Grid >= 31 (funnel/menu icon)
        cellStyle={"fontFamily": "'IBM Plex Mono', monospace"},
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
