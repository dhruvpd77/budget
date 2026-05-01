"""
Streamlit app: upload SBE-style budget Excel files, extract line items, explore analytics.
Run from project folder:  streamlit run app.py
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from budget_parser import load_folder_tidy, parse_sbe_excel

# —— Visual design tokens —————————————————————————————————————
ACCENTS = ["#818cf8", "#22d3ee", "#fb7185", "#a3e635", "#fbbf24", "#fdba74", "#c4b5fd", "#2dd4bf"]
LAYOUT: dict[str, Any] = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(17,24,39,0.72)",
    "font": {"color": "#e2e8f0", "size": 13, "family": "'Segoe UI', 'Inter', system-ui, sans-serif"},
    "margin": {"t": 52, "r": 20, "b": 56, "l": 56},
    "hoverlabel": {"bgcolor": "#1e293b", "font": {"size": 13, "color": "#f8fafc"}},
    "xaxis": {
        "showgrid": True,
        "gridcolor": "rgba(148,163,184,0.14)",
        "linecolor": "rgba(148,163,184,0.25)",
        "zeroline": False,
        "tickfont": {"color": "#94a3b8"},
        "title_font": {"color": "#cbd5e1", "size": 12},
    },
    "yaxis": {
        "showgrid": True,
        "gridcolor": "rgba(148,163,184,0.14)",
        "linecolor": "rgba(148,163,184,0.25)",
        "zeroline": False,
        "tickfont": {"color": "#94a3b8"},
        "title_font": {"color": "#cbd5e1", "size": 12},
    },
    "legend": {"bgcolor": "rgba(15,23,42,0.55)", "bordercolor": "rgba(129,140,248,0.35)", "borderwidth": 1},
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&display=swap');

html, body, [class*="css"]  {
  font-family: 'Outfit', 'Segoe UI', system-ui, sans-serif;
}

[data-testid="stAppViewContainer"] {
  background: radial-gradient(1200px 800px at 10% -10%, rgba(129,140,248,0.28) 0%, transparent 55%),
              radial-gradient(900px 500px at 100% 0%, rgba(34,211,238,0.18) 0%, transparent 50%),
              radial-gradient(800px 600px at 50% 120%, rgba(251,113,133,0.12) 0%, transparent 45%),
              linear-gradient(165deg, #070a12 0%, #0b1020 40%, #080c16 100%);
  background-attachment: fixed;
}

[data-testid="stHeader"] {
  background: rgba(7,10,18,0.72);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(129,140,248,0.2);
}

[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(17,24,39,0.94) 0%, rgba(8,12,22,0.98) 100%);
  border-right: 1px solid rgba(129,140,248,0.22);
  box-shadow: 8px 0 40px rgba(0,0,0,0.35);
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
  color: #a5b4fc !important;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.hero-wrap {
  padding: 1.25rem 0 0.5rem;
  margin-bottom: 0.25rem;
}
.hero-badge {
  display: inline-block;
  padding: 0.35rem 0.85rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  background: linear-gradient(90deg, rgba(129,140,248,0.35), rgba(34,211,238,0.28));
  border: 1px solid rgba(129,140,248,0.45);
  color: #c7d2fe;
  margin-bottom: 0.85rem;
}
.hero-title {
  font-size: clamp(1.85rem, 4vw, 2.65rem);
  font-weight: 800;
  letter-spacing: -0.04em;
  line-height: 1.1;
  margin: 0 0 0.35rem 0;
  background: linear-gradient(92deg, #f8fafc 0%, #c7d2fe 40%, #67e8f9 85%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.hero-sub {
  font-size: 1.05rem;
  color: #94a3b8;
  max-width: 52rem;
  line-height: 1.55;
  margin: 0 0 1rem 0;
}
.hero-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
.hero-pill {
  font-size: 0.78rem;
  font-weight: 600;
  padding: 0.35rem 0.75rem;
  border-radius: 10px;
  background: rgba(30,41,59,0.65);
  border: 1px solid rgba(148,163,184,0.25);
  color: #cbd5e1;
}

.section-card {
  border-radius: 16px;
  padding: 1.15rem 1.35rem 0.5rem;
  margin: 1.35rem 0 0.75rem;
  background: linear-gradient(145deg, rgba(17,24,39,0.72) 0%, rgba(15,23,42,0.42) 100%);
  border: 1px solid rgba(129,140,248,0.22);
  box-shadow: 0 24px 48px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.04);
}

.section-label {
  font-size: 0.68rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: #22d3ee;
  margin: 0 0 0.35rem 0;
}
.section-title {
  font-size: 1.35rem;
  font-weight: 700;
  color: #f1f5f9;
  margin: 0 0 0.45rem 0;
  letter-spacing: -0.03em;
}
.section-desc {
  font-size: 0.92rem;
  color: #94a3b8;
  line-height: 1.5;
  margin: 0;
}

[data-testid="stMetric"] {
  background: linear-gradient(160deg, rgba(30,41,59,0.75) 0%, rgba(15,23,42,0.55) 100%);
  border: 1px solid rgba(129,140,248,0.2);
  border-radius: 14px;
  padding: 1rem 1.1rem;
  box-shadow: 0 12px 32px rgba(0,0,0,0.2);
}
[data-testid="stMetric"] label {
  color: #a5b4fc !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
  color: #f8fafc !important;
  font-weight: 800;
}

[data-testid="stExpander"] {
  background: rgba(17,24,39,0.5);
  border: 1px solid rgba(99,102,241,0.25);
  border-radius: 12px;
}

[data-testid="stDataFrame"] {
  border: 1px solid rgba(129,140,248,0.2);
  border-radius: 12px;
  overflow: hidden;
}

div[data-testid="stVerticalBlock"] > div:has(> iframe) {
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid rgba(99,102,241,0.2);
  box-shadow: 0 16px 40px rgba(0,0,0,0.25);
}

.stDownloadButton button {
  background: linear-gradient(92deg, #6366f1 0%, #22d3ee 100%) !important;
  color: #0f172a !important;
  font-weight: 700 !important;
  border: none !important;
  border-radius: 12px !important;
  padding: 0.55rem 1.35rem !important;
}
.stDownloadButton button:hover {
  filter: brightness(1.08);
  box-shadow: 0 8px 24px rgba(99,102,241,0.45);
}

[data-testid="stAlert"] {
  border-radius: 12px;
}
</style>
"""


def _inject_design() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def _hero() -> None:
    st.markdown(
        """
        <div class="hero-wrap">
          <div class="hero-badge">Union budget · SBE analytics</div>
          <h1 class="hero-title">Budget Excel intelligence</h1>
          <p class="hero-sub">
            Turn Statement of Budget Estimates workbooks into vivid, interactive insight —
            by demand, period, subsection, and scheme — in seconds.
          </p>
          <div class="hero-pills">
            <span class="hero-pill">Multi-period Actuals / BE / RE</span>
            <span class="hero-pill">Revenue &amp; capital splits</span>
            <span class="hero-pill">Demand-level deep dives</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _section(label: str, title: str, desc: str | None = None) -> None:
    desc_html = f'<p class="section-desc">{desc}</p>' if desc else ""
    st.markdown(
        f"""
        <div class="section-card">
          <p class="section-label">{label}</p>
          <h2 class="section-title">{title}</h2>
          {desc_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _zest(fig: go.Figure) -> go.Figure:
    fig.update_layout(**LAYOUT)
    return fig


def _period_order(periods: list[str]) -> list[str]:
    """Sort periods in typical budget order: Actuals, then BE/RE by fiscal start year."""

    def sort_key(p: str) -> tuple[int, int]:
        p_low = p.lower()
        m = re.search(r"(\d{4})\s*-\s*(\d{4})", p)
        year = int(m.group(1)) if m else 9999
        if "actuals" in p_low:
            tier = 0
        elif "revised" in p_low:
            tier = 2
        else:
            tier = 1
        return (year, tier)

    return sorted(periods, key=sort_key)


@st.cache_data(show_spinner=False)
def parse_uploaded(name: str, blob: bytes) -> pd.DataFrame:
    parsed = parse_sbe_excel(blob)
    t = parsed.tidy.copy()
    t["source_file"] = name
    return t


def main() -> None:
    st.set_page_config(
        page_title="Budget Excel Analytics",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_design()
    _hero()

    sidebar = st.sidebar
    sidebar.markdown("### Control center")
    sidebar.caption("Data source · filters · scope")
    project_dir = Path(__file__).resolve().parent

    sidebar.subheader("Data source")
    use_local = sidebar.toggle(
        "Load all `.xlsx` from this folder",
        value=True,
        help=str(project_dir),
    )
    uploads = sidebar.file_uploader(
        "Or upload one or more `.xlsx` files",
        type=["xlsx"],
        accept_multiple_files=True,
    )

    frames: list[pd.DataFrame] = []

    if use_local:
        folder_df = load_folder_tidy(str(project_dir), "*.xlsx")
        if not folder_df.empty:
            frames.append(folder_df)

    if uploads:
        for f in uploads:
            raw = f.getvalue()
            try:
                frames.append(parse_uploaded(f.name, raw))
            except Exception as e:
                st.warning(f"Could not parse **{f.name}**: {e}")

    if not frames:
        st.info(
            f"Add `.xlsx` files to `{project_dir}` or upload them in the sidebar "
            "to begin."
        )
        return

    df = pd.concat(frames, ignore_index=True)

    for col, default in (
        ("demand_ministry", ""),
        ("demand_no", ""),
        ("demand_department", ""),
        ("demand_banner", ""),
    ):
        if col not in df.columns:
            df[col] = default

    df["demand_label"] = (
        df["demand_ministry"].fillna("").astype(str).str.strip()
        + " | Demand No. "
        + df["demand_no"].fillna("").astype(str).str.strip()
        + " | "
        + df["demand_department"].fillna("").astype(str).str.strip()
    )

    sidebar.divider()
    sidebar.subheader("Filters")
    files_sel = sidebar.multiselect(
        "Files",
        sorted(df["source_file"].unique()),
        default=sorted(df["source_file"].unique()),
    )
    df = df[df["source_file"].isin(files_sel)]

    comp_opts = ["Total", "Revenue", "Capital"]
    component = sidebar.selectbox("Amount type", comp_opts, index=0)

    row_kinds = sorted(df["row_kind"].dropna().unique())
    kind_pick = sidebar.multiselect(
        "Row types",
        row_kinds,
        default=[k for k in row_kinds if k in ("detail", "subtotal")],
    )
    search = sidebar.text_input("Search description", "")

    if kind_pick:
        df = df[df["row_kind"].isin(kind_pick)]

    q = search.strip().lower()
    df_before_search = df.copy()
    if q:
        df = df[df["description"].str.lower().str.contains(q, na=False)]

    if df.empty:
        st.warning("No rows after filters.")
        return

    deep_base = df_before_search[
        df_before_search["source_file"].isin(files_sel)
    ].copy()

    periods = _period_order(sorted(df["period"].unique()))
    latest = periods[-1] if periods else None
    prev = periods[-2] if len(periods) > 1 else None

    _section(
        "Overview",
        "Portfolio snapshot",
        "What you have loaded after filters — row counts, demands, and fiscal columns.",
    )
    m_cols = st.columns(3)
    m_cols[0].metric("Tidy rows", f"{len(df):,}")
    m_cols[1].metric("Demands in view", df["source_file"].nunique())
    m_cols[2].metric("Period columns", len(periods))

    catalog_cols = [
        c
        for c in (
            "demand_no",
            "demand_ministry",
            "demand_department",
            "source_file",
            "demand_banner",
        )
        if c in deep_base.columns
    ]
    catalog = deep_base[catalog_cols].drop_duplicates("source_file").copy()
    if "demand_no" in catalog.columns:
        catalog["_dno"] = pd.to_numeric(catalog["demand_no"], errors="coerce")
        catalog = catalog.sort_values("_dno", na_position="last").drop(
            columns="_dno", errors="ignore"
        )
    else:
        catalog = catalog.sort_values("source_file")

    st.caption(
        "Each row is one demand (workbook). Deep-dive below uses full demand data (ignores description search)."
    )
    st.dataframe(catalog, use_container_width=True, height=min(420, 38 + len(catalog) * 38), hide_index=True)

    _section(
        "Demand studio",
        "Detailed analytics by ministry block",
        "Subsections follow heading rows in each sheet (establishment, schemes, transfers, etc.).",
    )
    if deep_base.empty:
        st.warning("No rows available for demand-level analytics with the current filters.")
    else:
        labels_map: dict[str, str] = {}
        for sf in sorted(deep_base["source_file"].unique()):
            row0 = deep_base[deep_base["source_file"] == sf].iloc[0]
            lbl = str(row0.get("demand_label", sf))
            labels_map[f"{lbl} — {sf}"] = sf

        choice = st.selectbox(
            "Choose demand for detail",
            list(labels_map.keys()),
            index=0,
        )
        sf_sel = labels_map[choice]
        dmd = deep_base[deep_base["source_file"] == sf_sel]

        d_periods = _period_order(sorted(dmd["period"].unique()))
        d_latest = d_periods[-1] if d_periods else None
        d_prev = d_periods[-2] if len(d_periods) > 1 else None

        d_pivot_total = dmd[dmd["component"] == "Total"]
        k1, k2, k3, k4 = st.columns(4)
        if d_latest:
            k1.metric(
                f"Σ Total ({d_latest[:28]}…)" if len(d_latest) > 28 else f"Σ Total ({d_latest})",
                f"{d_pivot_total[d_pivot_total['period'] == d_latest]['value_cr'].sum():,.0f}",
                help="All extracted Total cells for this demand, after row-type filters.",
            )
        if d_prev and d_latest:
            a = d_pivot_total[d_pivot_total["period"] == d_latest]["value_cr"].sum()
            b = d_pivot_total[d_pivot_total["period"] == d_prev]["value_cr"].sum()
            k2.metric(
                "Δ vs prior period",
                f"{a - b:,.0f}",
                delta=f"{((a - b) / b * 100):.1f}%" if b else None,
                help=f"Prior: {d_prev}",
            )
        latest_rc = dmd[dmd["period"] == d_latest] if d_latest else dmd.iloc[0:0]
        if not latest_rc.empty:
            rev = latest_rc[latest_rc["component"] == "Revenue"]["value_cr"].sum()
            cap = latest_rc[latest_rc["component"] == "Capital"]["value_cr"].sum()
            k3.metric("Revenue (latest)", f"{rev:,.0f}")
            k4.metric("Capital (latest)", f"{cap:,.0f}")

        c_a, c_b = st.columns(2)
        with c_a:
            st.markdown("##### Totals by period")
            by_p = (
                d_pivot_total.groupby("period", as_index=False)["value_cr"]
                .sum()
                .set_index("period")
                .reindex(d_periods)
                .reset_index()
            )
            fig_d_line = px.line(
                by_p,
                x="period",
                y="value_cr",
                markers=True,
                labels={"value_cr": "Σ Total (₹ Cr)", "period": ""},
            )
            fig_d_line.update_traces(
                line=dict(width=4, color=ACCENTS[0]),
                marker=dict(size=12, line=dict(width=2, color="#0f172a")),
            )
            _zest(fig_d_line)
            st.plotly_chart(fig_d_line, use_container_width=True, config={"displayModeBar": False})
        with c_b:
            st.markdown("##### Revenue vs capital · latest")
            if d_latest:
                rc_d = (
                    dmd[dmd["period"] == d_latest]
                    .groupby("component", as_index=False)["value_cr"]
                    .sum()
                    .query("component in ['Revenue','Capital']")
                )
                if not rc_d.empty:
                    fig_rcd = px.bar(
                        rc_d,
                        x="component",
                        y="value_cr",
                        color="component",
                        color_discrete_sequence=[ACCENTS[1], ACCENTS[2]],
                        labels={"value_cr": "₹ Cr"},
                    )
                    _zest(fig_rcd)
                    st.plotly_chart(fig_rcd, use_container_width=True, config={"displayModeBar": False})

        st.markdown("##### Spending by sheet subsection · latest · line Total")
        sec_detail = dmd[
            (dmd["period"] == d_latest)
            & (dmd["component"] == "Total")
            & (dmd["row_kind"] == "detail")
        ].copy()
        sec_detail["subsection"] = (
            sec_detail["section"].fillna("").replace("", "(no subsection heading)")
        )
        if not sec_detail.empty:
            by_sec = (
                sec_detail.groupby("subsection", as_index=False)["value_cr"]
                .sum()
                .sort_values("value_cr", ascending=False)
            )
            fig_sec = px.bar(
                by_sec.head(35),
                x="value_cr",
                y="subsection",
                orientation="h",
                labels={"value_cr": "₹ Cr", "subsection": ""},
                color="value_cr",
                color_continuous_scale=["#1e1b4b", "#6366f1", "#22d3ee"],
            )
            fig_sec.update_layout(coloraxis_showscale=False, yaxis={"categoryorder": "total ascending"})
            _zest(fig_sec)
            st.plotly_chart(fig_sec, use_container_width=True, config={"displayModeBar": False})

            top_n_tree = st.slider("Treemap · top N lines by value", 20, 120, 60, key="tree_n")
            tree_df = sec_detail.nlargest(top_n_tree, "value_cr")
            fig_tree = px.treemap(
                tree_df,
                path=["subsection", "description"],
                values="value_cr",
                color="value_cr",
                color_continuous_scale="Turbo",
            )
            fig_tree.update_traces(marker=dict(line=dict(color="rgba(15,23,42,0.85)", width=1)))
            _zest(fig_tree)
            st.plotly_chart(fig_tree, use_container_width=True, config={"displayModeBar": False})

        st.markdown("##### Largest schemes & objects · latest")
        if not sec_detail.empty:
            top_s = (
                sec_detail.groupby(
                    ["subsection", "code", "description"], as_index=False
                )["value_cr"]
                .sum()
                .sort_values("value_cr", ascending=False)
                .head(25)
            )
            st.dataframe(
                top_s.style.format({"value_cr": "{:,.2f}"}),
                use_container_width=True,
                height=420,
            )

        st.markdown("##### Subsection mix · last two periods · Total ₹ Cr")
        if d_prev and d_latest and not sec_detail.empty:
            mix = (
                dmd[
                    (dmd["period"].isin([d_prev, d_latest]))
                    & (dmd["component"] == "Total")
                    & (dmd["row_kind"] == "detail")
                ]
                .assign(
                    subsection=lambda x: x["section"]
                    .fillna("")
                    .replace("", "(no subsection heading)")
                )
                .groupby(["period", "subsection"], as_index=False)["value_cr"]
                .sum()
            )
            wide = mix.pivot(index="subsection", columns="period", values="value_cr")
            period_cols_avail = [c for c in d_periods if c in wide.columns]
            if len(period_cols_avail) >= 2:
                wide = wide.reindex(columns=period_cols_avail[-2:])
                wide["change"] = wide.iloc[:, -1] - wide.iloc[:, -2]
                wide = wide.sort_values(wide.columns[1], ascending=False).head(30)
                st.dataframe(
                    wide.style.format("{:,.2f}"),
                    use_container_width=True,
                    height=400,
                )

        with st.expander("Top schemes inside each major subsection"):
            if not sec_detail.empty:
                for sub in by_sec.head(6)["subsection"]:
                    sub_lines = (
                        sec_detail[sec_detail["subsection"] == sub]
                        .groupby(["code", "description"], as_index=False)["value_cr"]
                        .sum()
                        .sort_values("value_cr", ascending=False)
                        .head(12)
                    )
                    if sub_lines.empty:
                        continue
                    st.markdown(f"**{sub}**")
                    st.dataframe(
                        sub_lines.style.format({"value_cr": "{:,.2f}"}),
                        use_container_width=True,
                        height=260,
                    )

    st.divider()
    _section(
        "Macro view",
        "Cross-demand analytics",
        "Compare files, periods, and top movers with the global filters and amount type.",
    )
    pivot_src = df[df["component"] == component]
    by_pf = (
        pivot_src.groupby(["period", "source_file"], as_index=False)["value_cr"]
        .sum()
        .sort_values("period")
    )
    fig_period_file = px.bar(
        by_pf,
        x="period",
        y="value_cr",
        color="source_file",
        barmode="group",
        labels={"value_cr": f"{component} (₹ Cr)", "period": "Period"},
        color_discrete_sequence=ACCENTS,
    )
    fig_period_file.update_layout(xaxis_tickangle=-25, legend_title_text="File")
    _zest(fig_period_file)
    st.plotly_chart(fig_period_file, use_container_width=True, config={"displayModeBar": False})

    agg_period = pivot_src.groupby("period", as_index=False)["value_cr"].sum()
    agg_period = agg_period.set_index("period").reindex(periods).reset_index()
    c1, c2 = st.columns(2)
    with c1:
        fig_line = px.line(
            agg_period,
            x="period",
            y="value_cr",
            markers=True,
            labels={"value_cr": f"Σ {component} (₹ Cr)", "period": ""},
        )
        fig_line.update_traces(
            line=dict(width=4, color=ACCENTS[3]),
            marker=dict(size=11, color=ACCENTS[4], line=dict(color="#0f172a", width=2)),
        )
        _zest(fig_line)
        st.plotly_chart(fig_line, use_container_width=True, config={"displayModeBar": False})
    with c2:
        fig_pie = px.pie(
            agg_period.dropna(subset=["value_cr"]),
            names="period",
            values="value_cr",
            hole=0.38,
            color_discrete_sequence=ACCENTS,
        )
        fig_pie.update_traces(textfont_color="#f8fafc", marker=dict(line=dict(color="#0f172a", width=1.2)))
        _zest(fig_pie)
        st.plotly_chart(fig_pie, use_container_width=True, config={"displayModeBar": False})

    st.markdown("##### Revenue vs capital · latest · all loaded demands")
    if latest:
        latest_df = df[df["period"] == latest]
        rc = (
            latest_df.groupby("component", as_index=False)["value_cr"]
            .sum()
            .query("component in ['Revenue','Capital']")
        )
        if not rc.empty:
            fig_rc = px.bar(
                rc,
                x="component",
                y="value_cr",
                color="component",
                color_discrete_sequence=[ACCENTS[1], ACCENTS[5]],
                labels={"value_cr": "₹ Cr"},
            )
            _zest(fig_rc)
            st.plotly_chart(fig_rc, use_container_width=True, config={"displayModeBar": False})

    st.markdown("##### Top line items · latest · Total · detail rows")
    top_n = st.slider("Rows to show", 5, 50, 15)
    if latest:
        top_df = df[
            (df["period"] == latest)
            & (df["component"] == "Total")
            & (df["row_kind"] == "detail")
        ]
        top_sum = (
            top_df.groupby(
                ["source_file", "section", "code", "description"], as_index=False
            )["value_cr"]
            .sum()
            .sort_values("value_cr", ascending=False)
            .head(top_n)
        )
        st.dataframe(
            top_sum.style.format({"value_cr": "{:,.2f}"}),
            use_container_width=True,
            height=min(420, 40 + top_n * 35),
        )

    st.markdown("##### Period change · largest movers · Total · detail")
    if latest and prev:
        d_latest_df = df[
            (df["period"] == latest)
            & (df["component"] == "Total")
            & (df["row_kind"] == "detail")
        ]
        d_prev_df = df[
            (df["period"] == prev)
            & (df["component"] == "Total")
            & (df["row_kind"] == "detail")
        ]
        k = ["source_file", "section", "code", "description"]
        m1 = d_latest_df.groupby(k, as_index=False)["value_cr"].sum()
        m2 = d_prev_df.groupby(k, as_index=False)["value_cr"].sum()
        ch = m1.merge(m2, on=k, how="outer", suffixes=("_new", "_old")).fillna(0.0)
        ch["change_cr"] = ch["value_cr_new"] - ch["value_cr_old"]
        ch["pct"] = ch.apply(
            lambda r: (r["change_cr"] / r["value_cr_old"] * 100)
            if r["value_cr_old"] not in (0, None)
            else None,
            axis=1,
        )
        ch = ch.sort_values("change_cr", key=abs, ascending=False).head(25)
        st.dataframe(
            ch.rename(
                columns={
                    "value_cr_new": latest[:22],
                    "value_cr_old": prev[:22],
                }
            ).style.format(
                {
                    latest[:22]: "{:,.2f}",
                    prev[:22]: "{:,.2f}",
                    "change_cr": "{:,.2f}",
                    "pct": "{:.1f}%",
                }
            ),
            use_container_width=True,
            height=480,
        )

    st.markdown("##### Heatmap · file × period totals")
    heat = (
        pivot_src.groupby(["source_file", "period"], as_index=False)["value_cr"]
        .sum()
        .pivot(index="source_file", columns="period", values="value_cr")
        .reindex(columns=periods)
    )
    if not heat.empty and heat.shape[1] > 1:
        fig_h = go.Figure(
            data=go.Heatmap(
                z=heat.values,
                x=[str(c) for c in heat.columns],
                y=list(heat.index),
                colorscale=[
                    [0, "#0f172a"],
                    [0.35, "#312e81"],
                    [0.6, "#6366f1"],
                    [0.85, "#22d3ee"],
                    [1, "#a5f3fc"],
                ],
                hoverongaps=False,
            )
        )
        fig_h.update_layout(
            xaxis_tickangle=-20,
            yaxis_autorange="reversed",
            height=80 + 28 * len(heat.index),
        )
        _zest(fig_h)
        st.plotly_chart(fig_h, use_container_width=True, config={"displayModeBar": False})

    st.markdown("##### Export")
    st.download_button(
        "Download tidy CSV (filtered)",
        df.to_csv(index=False).encode("utf-8"),
        file_name="budget_tidy_filtered.csv",
        mime="text/csv",
    )

    with st.expander("Raw tidy preview · first 500 rows"):
        st.dataframe(df.head(500), use_container_width=True)

    st.markdown(
        """
        <div style="text-align:center;color:#64748b;font-size:0.8rem;margin:2.5rem 0 1rem">
          Built with Streamlit · SBE parser · Plotly
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
