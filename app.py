"""
Streamlit app: upload SBE-style budget Excel files, extract line items, explore analytics.
Run from project folder:  streamlit run app.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from budget_parser import load_folder_tidy, parse_sbe_excel

st.set_page_config(
    page_title="Budget Excel Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


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
    st.title("Budget Excel analytics")
    st.caption(
        "Extracts Union Budget SBE exports (`SBEDataWithoutNote`) into tidy figures "
        "and compares periods, revenue vs capital, and line items."
    )

    sidebar = st.sidebar
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

    st.subheader("Extracted metadata")
    m_cols = st.columns(3)
    m_cols[0].metric("Rows (tidy)", f"{len(df):,}")
    m_cols[1].metric("Demands in view", df["source_file"].nunique())
    m_cols[2].metric("Period columns found", len(periods))

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
    catalog = (
        deep_base[catalog_cols].drop_duplicates("source_file").copy()
    )
    if "demand_no" in catalog.columns:
        catalog["_dno"] = pd.to_numeric(catalog["demand_no"], errors="coerce")
        catalog = catalog.sort_values("_dno", na_position="last").drop(
            columns="_dno", errors="ignore"
        )
    else:
        catalog = catalog.sort_values("source_file")
    st.caption(
        "Each row is one demand (one workbook). Use the deep-dive below for subsection and scheme-level analytics."
    )
    st.dataframe(catalog, use_container_width=True, height=min(420, 38 + len(catalog) * 38), hide_index=True)

    st.subheader("Detailed analytics by demand")
    st.caption(
        "Subsections come from heading rows in the sheet (for example establishment, central schemes, transfers). "
        "Deep-dive ignores the description search box so you always see the full demand."
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
                f"Δ vs prior period",
                f"{a - b:,.0f}",
                delta=f"{((a - b) / b * 100):.1f}%" if b else None,
                help=f"Prior: {d_prev}",
            )
        latest_rc = dmd[dmd["period"] == d_latest] if d_latest else dmd.iloc[0:0]
        if not latest_rc.empty:
            rev = latest_rc[latest_rc["component"] == "Revenue"]["value_cr"].sum()
            cap = latest_rc[latest_rc["component"] == "Capital"]["value_cr"].sum()
            k3.metric("Revenue (latest, all rows)", f"{rev:,.0f}")
            k4.metric("Capital (latest, all rows)", f"{cap:,.0f}")

        c_a, c_b = st.columns(2)
        with c_a:
            st.markdown("**Totals by period**")
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
            fig_d_line.update_traces(line_width=3)
            st.plotly_chart(fig_d_line, use_container_width=True)
        with c_b:
            st.markdown("**Revenue vs capital (latest period)**")
            if d_latest:
                rc_d = (
                    dmd[dmd["period"] == d_latest]
                    .groupby("component", as_index=False)["value_cr"]
                    .sum()
                    .query("component in ['Revenue','Capital']")
                )
                if not rc_d.empty:
                    st.plotly_chart(
                        px.bar(
                            rc_d,
                            x="component",
                            y="value_cr",
                            color="component",
                            labels={"value_cr": "₹ Cr"},
                        ),
                        use_container_width=True,
                    )

        st.markdown("**Spending by sheet subsection (latest, line-level Total)**")
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
            )
            fig_sec.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_sec, use_container_width=True)

            top_n_tree = st.slider("Treemap: how many lines", 20, 120, 60, key="tree_n")
            tree_df = sec_detail.nlargest(top_n_tree, "value_cr")
            st.plotly_chart(
                px.treemap(
                    tree_df,
                    path=["subsection", "description"],
                    values="value_cr",
                    color="value_cr",
                    color_continuous_scale="Blues",
                ),
                use_container_width=True,
            )

        st.markdown("**Largest schemes / objects (latest)**")
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

        st.markdown("**Subsection mix across periods (Total ₹ Cr)**")
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
    st.subheader("Totals by period and file")
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
    )
    fig_period_file.update_layout(xaxis_tickangle=-25, legend_title_text="File")
    st.plotly_chart(fig_period_file, use_container_width=True)

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
        fig_line.update_traces(line_width=3)
        st.plotly_chart(fig_line, use_container_width=True)
    with c2:
        fig_pie = px.pie(
            agg_period.dropna(subset=["value_cr"]),
            names="period",
            values="value_cr",
            hole=0.35,
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    st.subheader("Revenue vs capital (latest period)")
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
                labels={"value_cr": "₹ Cr"},
            )
            st.plotly_chart(fig_rc, use_container_width=True)

    st.subheader("Top line items (latest period, Total)")
    top_n = st.slider("How many rows", 5, 50, 15)
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

    st.subheader("Period change (same line, Total)")
    if latest and prev:
        d_latest = df[
            (df["period"] == latest)
            & (df["component"] == "Total")
            & (df["row_kind"] == "detail")
        ]
        d_prev = df[
            (df["period"] == prev)
            & (df["component"] == "Total")
            & (df["row_kind"] == "detail")
        ]
        k = ["source_file", "section", "code", "description"]
        m1 = d_latest.groupby(k, as_index=False)["value_cr"].sum()
        m2 = d_prev.groupby(k, as_index=False)["value_cr"].sum()
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

    st.subheader("Correlation heatmap (files × period totals)")
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
                x=list(heat.columns),
                y=list(heat.index),
                colorscale="Blues",
                hoverongaps=False,
            )
        )
        fig_h.update_layout(
            xaxis_tickangle=-20,
            yaxis_autorange="reversed",
            height=80 + 28 * len(heat.index),
        )
        st.plotly_chart(fig_h, use_container_width=True)

    st.subheader("Download tidy extract")
    st.download_button(
        "Download CSV (filtered)",
        df.to_csv(index=False).encode("utf-8"),
        file_name="budget_tidy_filtered.csv",
        mime="text/csv",
    )

    with st.expander("Raw tidy preview"):
        st.dataframe(df.head(500), use_container_width=True)


if __name__ == "__main__":
    main()
