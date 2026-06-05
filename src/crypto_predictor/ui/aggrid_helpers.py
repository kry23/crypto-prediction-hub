"""AG-Grid tables that match the Midnight Desk theme.

Streamlit's native ``st.dataframe`` is a canvas grid — CSS can't touch it, so it
stays light/grey no matter the theme. This wraps ``streamlit-aggrid`` (a real
DOM grid) instead.

Note on theming: st_aggrid 1.2.x bundles AG-Grid's *new* Theming API, which
dropped the old ``.ag-theme-alpine`` CSS classes and CSS variables — so
``custom_css`` selectors targeting them do nothing. The reliable path is
``theme="streamlit"``, which inherits the active Streamlit theme (dark here, set
in ``.streamlit/config.toml``). Per-cell colour still works because ``cellStyle``
goes through grid options, independent of the theme.
"""
from __future__ import annotations

from typing import Sequence

import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

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
    """Render ``data`` as a dark, theme-matched AG-Grid (display-only).

    ``color_cols`` are signed numeric columns coloured by sign. ``key`` must be
    unique per grid on a page.
    """
    df = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    if df.empty:
        return

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(sortable=True, resizable=True, filter=False)
    for col in color_cols:
        if col in df.columns:
            gb.configure_column(col, cellStyle=_SIGN_COLOR)
    options = gb.build()
    options["domLayout"] = "autoHeight"                  # size to content
    options["autoSizeStrategy"] = {"type": "fitGridWidth"}  # fill width

    AgGrid(
        df,
        gridOptions=options,
        theme="streamlit",       # inherits the dark Streamlit theme
        allow_unsafe_jscode=True,
        update_on=[],            # display only — no reruns on sort
        key=key,
        show_toolbar=False,
        show_search=False,
        show_download_button=False,
    )
