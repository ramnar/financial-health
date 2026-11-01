"""
Portfolio & cash-flow analytics dashboard.

    streamlit run app.py                         # synthetic data in data_sample/
    ANALYTICS_DATA=data streamlit run app.py     # real data (after extract.py)
"""
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import metrics as m

ROOT = Path(__file__).parent
DATA = ROOT / os.environ.get("ANALYTICS_DATA", "data_sample")
IS_SAMPLE = DATA.name == "data_sample"
# Each data set may carry its own ranges; real data falls back to the shared file
TARGETS = DATA / "targets.ini" if (DATA / "targets.ini").exists() else ROOT / "targets.ini"

st.set_page_config(page_title="Portfolio Analytics", page_icon="₹", layout="wide")

# ── Palette (validated categorical order; dark steps chosen for dark surface) ─
DARK = st.context.theme.type == "dark"
SERIES = (["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"] if DARK else
          ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"])
MUTED = "#898781"
BAND = "#383835" if DARK else "#e1e0d9"
STATUS = {"In range": ("#0ca30c", "✓"), "Below range": ("#fab219", "▼"),
          "Above range": ("#fab219", "▲"), "No recommendation": (MUTED, "–")}
DIVERGING = ("#2a78d6", "#f0efec" if not DARK else "#383835", "#e34948")

# Colour follows the entity everywhere it appears
CLASS_COLOR = dict(zip(m.ASSET_CLASSES + ["Other"], SERIES))
INCOME, EXPENSE, SAVINGS = SERIES[0], SERIES[1], SERIES[2]


# ── Formatting ────────────────────────────────────────────────────────────────

def inr(v: float, signed: bool = False) -> str:
    """Indian-style short money: ₹2.99 Cr, ₹3.21 L, ₹73,200."""
    if v is None or np.isnan(v):
        return "–"
    sign = ("+" if v > 0 else "−" if v < 0 else "") if signed else ("−" if v < 0 else "")
    a = abs(v)
    if a >= 1e7:
        return f"{sign}₹{a / 1e7:.2f} Cr"
    if a >= 1e5:
        return f"{sign}₹{a / 1e5:.2f} L"
    return f"{sign}₹{a:,.0f}"


def style(fig: go.Figure, y_title: str = "", height: int = 340, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), hovermode="x unified",
        showlegend=legend, legend=dict(orientation="h", y=1.08, x=0, title=None),
        yaxis_title=y_title, xaxis_title=None,
    )
    fig.update_xaxes(showgrid=False)
    return fig


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, config={"displayModeBar": False})


# ── Data ──────────────────────────────────────────────────────────────────────

if not (DATA / "cashflow.csv").exists():
    st.title("Portfolio Analytics")
    st.info(f"No data in `{DATA.name}/`. Generate sample data or extract your real data:\n\n"
            "```\npython make_sample_data.py\n# or\npython capture_rr2ff.py && python extract.py\n```")
    st.stop()


@st.cache_data
def load(data_dir: Path, mtime: float) -> dict[str, pd.DataFrame]:
    return m.load_data(data_dir)


d = load(DATA, (DATA / "cashflow.csv").stat().st_mtime)
today = pd.Timestamp(datetime.now())

nw = m.mark_missing(d["networth"], ["assets", "networth"])
eq = m.mark_missing(d["equity_pct"], ["equity_pct"])
roi = d["roi"].dropna()
cf_all = m.complete_months(d["cashflow"], today)
alloc = m.class_allocation(d["asset_split"])
portfolio_total = alloc["value"].sum()
status = m.balance_status(alloc, m.load_targets(TARGETS),
                          m.latest_targets(d["strategy"]))
eh = d["expense_heads"]

missing = nw.loc[nw["networth"].isna(), "month"].dt.strftime("%b %Y").tolist()
captured = datetime.fromtimestamp((DATA / "cashflow.csv").stat().st_mtime)

# ── Header ────────────────────────────────────────────────────────────────────

st.title("Portfolio Analytics")
if IS_SAMPLE:
    st.warning("Showing **synthetic sample data**. To view your real data, run "
               "`ANALYTICS_DATA=data streamlit run app.py`.", icon=":material/science:")
source = "Synthetic sample data, generated" if IS_SAMPLE else "Source: RR2FF, extracted"
st.caption(f"{source} {captured:%d %b %Y}. "
           f"Cash flow through {cf_all['month'].max():%b %Y} (current month excluded as incomplete).")

nw_now, nw_delta = m.latest_change(nw["networth"])
plan_now = nw.dropna(subset=["networth"]).iloc[-1]["planned_networth"]
roi_now, roi_delta = m.latest_change(roi["roi_pct"])
t12 = m.trailing_summary(cf_all)
prev12 = m.trailing_summary(cf_all.iloc[:-12])
spark = cf_all.tail(12)

k = st.columns(5)
k[0].metric("Portfolio value", inr(portfolio_total),
            delta=f"{inr(nw_now - plan_now, signed=True)} vs plan "
                  f"({nw.dropna(subset=['networth'])['month'].iloc[-1]:%b})", border=True,
            chart_data=nw["networth"].dropna().tolist(), chart_type="area",
            help="Current value from the portfolio split. Sparkline: month-end values (missing months skipped).")
k[1].metric("ROI", f"{roi_now:.2f}%", delta=f"{roi_delta:+.2f} pts" if roi_delta else None,
            border=True, chart_data=roi["roi_pct"].tail(12).tolist())
k[2].metric("Savings rate · last 12 mo", f"{t12['savings_rate']:.1f}%",
            delta=f"{t12['savings_rate'] - prev12['savings_rate']:+.1f} pts vs prior 12 mo", border=True,
            chart_data=spark["savings_rate"].round(1).tolist())
k[3].metric("Avg monthly expense · 12 mo", inr(t12["avg_expense"]),
            delta=f"{100 * (t12['avg_expense'] / prev12['avg_expense'] - 1):+.1f}% vs prior 12 mo",
            delta_color="inverse", border=True, chart_data=spark["expense"].tolist(), chart_type="bar")
in_range = (status["status"] == "In range").sum()
judged = (status["status"] != "No recommendation").sum()
k[4].metric("Allocation", f"{in_range} of {judged} in range",
            delta="Balanced" if in_range == judged else "Rebalance needed",
            delta_color="normal" if in_range == judged else "inverse", delta_arrow="off", border=True)

tab_nw, tab_cf, tab_sp, tab_rb = st.tabs(["Net worth & portfolio", "Cash flow", "Spending", "Rebalancing"])

# ── Net worth & portfolio ─────────────────────────────────────────────────────

with tab_nw:
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("Net worth vs plan")
        fig = go.Figure()
        fig.add_scatter(x=nw["month"], y=nw["planned_networth"] / 1e7, name="Plan",
                        line=dict(color=MUTED, width=2, dash="dash"), hovertemplate="₹%{y:.2f} Cr")
        fig.add_scatter(x=nw["month"], y=nw["networth"] / 1e7, name="Actual", mode="lines+markers",
                        connectgaps=True, line=dict(color=SERIES[0], width=2),
                        marker=dict(size=8), hovertemplate="₹%{y:.2f} Cr")
        show(style(fig, "₹ crore"))
        if missing:
            st.caption(f"No portfolio update recorded for {', '.join(missing)}. "
                       "The line bridges those months instead of dropping to zero.")
        liabilities = d["networth"]["liabilities"].iloc[-1]
        st.caption(f"Liabilities: {inr(liabilities)} — net worth equals total assets.")

    with right:
        st.subheader("Where it's invested")
        tree = m.asset_tree(d["asset_split"])
        classes = tree.groupby("asset_class", as_index=False)["value"].sum()
        fig = go.Figure(go.Treemap(
            ids=list(classes["asset_class"]) + [f"{c}/{n}" for c, n in zip(tree["asset_class"], tree["name"])],
            labels=list(classes["asset_class"]) + list(tree["name"]),
            parents=[""] * len(classes) + list(tree["asset_class"]),
            values=list(classes["value"]) + list(tree["value"]),
            branchvalues="total",
            marker=dict(colors=[CLASS_COLOR[c] for c in classes["asset_class"]]
                        + [CLASS_COLOR[c] for c in tree["asset_class"]],
                        line=dict(width=2)),
            texttemplate="<b>%{label}</b><br>%{percentRoot:.1%}",
            textfont=dict(color="white"),
            hovertemplate="<b>%{label}</b><br>%{value:,.0f}<br>%{percentRoot:.1%} of portfolio<extra></extra>",
            tiling=dict(pad=2),
        ))
        fig.update_layout(height=360, margin=dict(l=0, r=0, t=0, b=0))
        show(fig)
        st.caption("Click a class to zoom into its assets.")

    st.subheader("Return on investment")
    fig = go.Figure()
    fig.add_scatter(x=roi["month"], y=roi["roi_pct"], name="ROI", mode="lines+markers",
                    line=dict(color=SERIES[0], width=2), marker=dict(size=6),
                    hovertemplate="%{y:.2f}%")
    show(style(fig, "ROI %", height=280, legend=False))

# ── Cash flow ─────────────────────────────────────────────────────────────────

with tab_cf:
    period = st.segmented_control("Period", ["1Y", "2Y", "3Y", "All"], default="3Y",
                                  required=True, key="cf_period")
    cf = m.filter_period(cf_all, period)
    s = m.trailing_summary(cf, months=len(cf))

    c = st.columns(4)
    c[0].metric("Avg monthly income", inr(s["income"] / len(cf)), border=True)
    c[1].metric("Avg monthly expense", inr(s["expense"] / len(cf)), border=True)
    c[2].metric("Total saved", inr(s["savings"]), delta=f"{s['savings_rate']:.1f}% of income",
                delta_arrow="off", delta_color="off", border=True)
    trend = m.annual_trend(cf, "expense")
    c[3].metric("Expense growth · per year", f"{inr(trend, signed=True)}/mo", border=True,
                help="Slope of a straight line fitted through monthly expenses: how much "
                     "the typical month's spend grows each year.")

    st.subheader("Income and expense")
    fig = go.Figure()
    avg_max = 0.0
    for col, name, color in (("income", "Income", INCOME), ("expense", "Expense", EXPENSE)):
        fig.add_scatter(x=cf["month"], y=cf[col] / 1e5, name=name, mode="lines+markers",
                        line=dict(color=color, width=1), marker=dict(size=5), opacity=0.45,
                        legendgroup=name, hovertemplate="₹%{y:.2f} L")
        avg = m.rolling_mean(cf_all.set_index("month")[col]).reindex(cf["month"])
        avg_max = max(avg_max, avg.max())
        fig.add_scatter(x=cf["month"], y=avg.values / 1e5, name=f"{name} · 6-mo avg",
                        line=dict(color=color, width=2.5), legendgroup=name,
                        hovertemplate="₹%{y:.2f} L")
    # Keep one-off spikes (e.g. a bonus) from flattening every other month
    spikes = cf[cf["income"] > 2 * cf["income"].median()]

    def clip_spikes(fig, values: pd.Series, extra: float = 0.0) -> None:
        cap = max(values[~values.index.isin(spikes.index)].max(), extra) * 1.15 / 1e5
        fig.update_yaxes(range=[0, cap])
        for r in spikes.itertuples():
            fig.add_annotation(x=r.month, y=cap, text=f"↑ {inr(values[r.Index])}", showarrow=False,
                               xanchor="left", yanchor="top", font=dict(size=11, color=MUTED))

    if not spikes.empty:
        clip_spikes(fig, cf[["income", "expense"]].max(axis=1), avg_max)
    show(style(fig, "₹ lakh", height=360))
    if not spikes.empty:
        st.caption("One-off income spikes are clipped at the top of the chart: " + ", ".join(
            f"{r.month:%b %Y} ({inr(r.income)})" for r in spikes.itertuples())
            + ". The 6-month average smooths them out.")

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Monthly savings vs plan")
        fig = go.Figure()
        fig.add_bar(x=cf["month"], y=cf["savings"] / 1e5, name="Saved", marker_color=SAVINGS,
                    marker_line_width=0, hovertemplate="₹%{y:.2f} L")
        fig.add_scatter(x=cf["month"], y=cf["savings_baseline"] / 1e5, name="Freedom plan baseline",
                        line=dict(color=MUTED, width=2, dash="dash"), hovertemplate="₹%{y:.2f} L")
        fig.update_layout(bargap=0.25)
        if not spikes.empty:
            clip_spikes(fig, cf["savings"], cf["savings_baseline"].max())
        show(style(fig, "₹ lakh", height=300))
        below = (cf["savings"] < cf["savings_baseline"]).sum()
        st.caption(f"Below the baseline in {below} of {len(cf)} months.")
    with right:
        st.subheader("Savings rate")
        fig = go.Figure()
        fig.add_scatter(x=cf["month"], y=cf["savings_rate"], name="Savings rate",
                        line=dict(color=SAVINGS, width=2), mode="lines", fill="tozeroy",
                        fillcolor="rgba(27,175,122,0.12)", hovertemplate="%{y:.1f}%")
        fig.update_yaxes(range=[0, 100], ticksuffix="%")
        show(style(fig, "", height=300, legend=False))
        st.caption("Share of each month's income left after expenses.")

# ── Spending ──────────────────────────────────────────────────────────────────

with tab_sp:
    years = sorted(eh["year"].unique(), reverse=True)
    year = st.segmented_control("Year", years, default=years[0], required=True, key="sp_year")
    partial = year == today.year

    top = m.top_heads(eh, year)
    prev = eh[eh["year"] == year - 1].set_index("head")["monthly_avg"]
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader(f"Where the money went in {year}" + (" (so far)" if partial else ""))
        top = top.iloc[::-1]  # largest at top
        fig = go.Figure()
        fig.add_bar(y=top["head"], x=top["monthly_avg"], orientation="h", name=str(year),
                    marker_color=SERIES[1], marker_line_width=0,
                    hovertemplate="%{y}: ₹%{x:,.0f}/mo<extra></extra>")
        prev_vals = top["head"].map(prev)
        if year - 1 in eh["year"].values:
            fig.add_scatter(y=top["head"], x=prev_vals, mode="markers", name=str(year - 1),
                            marker=dict(symbol="line-ns", size=14, line=dict(width=2.5, color=MUTED)),
                            hovertemplate="%{y}: ₹%{x:,.0f}/mo in " + str(year - 1) + "<extra></extra>")
        fig.update_layout(hovermode="closest", bargap=0.3)
        fig.update_xaxes(showgrid=True, tickprefix="₹", separatethousands=True)
        show(style(fig, "", height=460).update_layout(hovermode="closest"))
        st.caption("Bars: average monthly spend. Grey ticks: same head the year before.")

    with right:
        st.subheader("Household inflation")
        totals = eh.groupby("year")["monthly_avg"].sum()
        ti = m.total_inflation(eh)
        c = st.columns(3)
        for col, n in zip(c, (1, 2, 3)):
            col.metric(f"{n}-yr · per year", f"{ti[f'infl_{n}y']:+.0f}%", border=True)
        fig = go.Figure()
        fig.add_bar(x=totals.index.astype(str), y=totals.values / 1e3, marker_color=SERIES[1],
                    marker_line_width=0, hovertemplate="₹%{y:.1f}k/mo<extra></extra>")
        fig.update_layout(bargap=0.4)
        show(style(fig, "₹ thousand / month", height=250, legend=False))
        st.caption(f"Average monthly household spend by year. {today.year} covers Jan–"
                   f"{(today - pd.DateOffset(months=1)):%b} only, so it's compared as a monthly average.")

    st.subheader("Every expense head")
    hi = m.head_inflation(eh)
    yrs = sorted(c for c in hi.columns if isinstance(c, (int, np.integer)))
    hi = hi.sort_values(yrs[-1], ascending=False)
    pct_cols = {"1-yr %": "infl_1y", "2-yr %/yr": "infl_2y", "3-yr %/yr": "infl_3y"}
    table = pd.DataFrame({
        "Head": hi.index,
        "Trend": hi[yrs].values.tolist(),
        f"{yrs[-1]} ₹/mo": hi[yrs[-1]].values,
        f"{yrs[-2]} ₹/mo": hi[yrs[-2]].values,
        # Text, so an undefined value reads "–" rather than "None"
        **{label: hi[src].map(lambda v: "–" if pd.isna(v) else f"{v:+.0f}%").values
           for label, src in pct_cols.items()},
    })

    def heat(v):
        if pd.isna(v):
            return ""
        t = min(abs(v), 100) / 100
        hexc = DIVERGING[2] if v > 0 else DIVERGING[0]
        r, g, b = (int(hexc[i:i + 2], 16) for i in (1, 3, 5))
        return f"background-color: rgba({r},{g},{b},{0.12 + 0.5 * t:.2f})"

    styler = table.style
    for label, src in pct_cols.items():
        styler = styler.apply(lambda _, s=src: [heat(v) for v in hi[s]], subset=[label])
    st.dataframe(
        styler, hide_index=True, height=520,
        column_config={
            "Trend": st.column_config.LineChartColumn(f"Monthly avg {yrs[0]}–{yrs[-1]}", y_min=0),
            f"{yrs[-1]} ₹/mo": st.column_config.NumberColumn(format="localized"),
            f"{yrs[-2]} ₹/mo": st.column_config.NumberColumn(format="localized"),
        },
    )
    st.caption("Inflation = change in average monthly spend, averaged per year (RR2FF's method). "
               "Red: spending up; blue: spending down; – : nothing spent in the base year.")

    bk = d["breakup"]
    if not bk.empty:
        st.subheader("Single-month breakup")
        months = sorted(bk["month"].unique(), reverse=True)
        pick = st.selectbox("Month", months, format_func=lambda x: f"{pd.Timestamp(x):%b %Y}")
        cols = st.columns(2, gap="large")
        for col, cat, color in zip(cols, ("Income", "Expense"), (INCOME, EXPENSE)):
            rows = bk[(bk["month"] == pick) & (bk["category"] == cat) & (bk["amount"] > 0)]
            rows = rows.sort_values("amount")
            with col:
                st.markdown(f"**{cat}** · {inr(rows['amount'].sum())}")
                fig = go.Figure(go.Bar(
                    y=rows["head"].str.slice(0, 32), x=rows["amount"], orientation="h",
                    marker_color=color, marker_line_width=0,
                    text=(100 * rows["amount"] / rows["amount"].sum()).map("{:.0f}%".format),
                    textposition="outside", cliponaxis=False,
                    hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>"))
                fig.update_xaxes(tickprefix="₹", separatethousands=True,
                                 range=[0, rows["amount"].max() * 1.12])
                show(style(fig, "", height=60 + 28 * len(rows), legend=False)
                     .update_layout(hovermode="closest"))
        if len(months) == 1:
            st.caption("Only one month was captured. Re-run `capture_rr2ff.py` to fetch the other months.")

# ── Rebalancing ───────────────────────────────────────────────────────────────

with tab_rb:
    st.subheader("Allocation vs recommended range")
    rb = status.iloc[::-1]  # Equity on top
    fig = go.Figure()
    has_range = rb["low"].notna()
    fig.add_bar(y=rb.loc[has_range, "asset_class"], x=rb.loc[has_range, "high"] - rb.loc[has_range, "low"],
                base=rb.loc[has_range, "low"], orientation="h", name="Recommended range",
                marker=dict(color=BAND, line_width=0), width=0.5,
                customdata=rb.loc[has_range, "high"],
                hovertemplate="%{y}: %{base:.0f}% – %{customdata:.0f}%<extra>Recommended</extra>")
    fig.add_scatter(y=rb["asset_class"], x=rb["target"], mode="markers", name="Advisor target",
                    marker=dict(symbol="line-ns", size=22, line=dict(width=2.5, color=MUTED)),
                    hovertemplate="%{y}: target %{x:.0f}%<extra></extra>")
    fig.add_scatter(y=rb["asset_class"], x=rb["pct"], mode="markers+text", showlegend=False,
                    marker=dict(size=14, color=[CLASS_COLOR[c] for c in rb["asset_class"]],
                                line=dict(width=2, color="#fcfcfb" if not DARK else "#1a1a19")),
                    text=[f"  {p:.1f}%" for p in rb["pct"]], textposition="middle right",
                    hovertemplate="%{y}: %{x:.2f}%<extra>Actual</extra>")
    # Legend entry in neutral ink: the dots themselves wear each class's colour
    fig.add_scatter(x=[None], y=[None], mode="markers", name="Actual",
                    marker=dict(size=12, color=MUTED))
    fig.update_xaxes(range=[0, 70], ticksuffix="%", showgrid=True)
    fig.update_yaxes(categoryorder="array", categoryarray=list(rb["asset_class"]))
    fig.update_layout(hovermode="closest", barmode="overlay")
    show(style(fig, "", height=320))

    cols = st.columns(len(status))
    for col, r in zip(cols, status.itertuples()):
        color, icon = STATUS[r.status]
        if r.rebalance_amount > 0:
            action = f"Add {inr(r.rebalance_amount)}"
        elif r.rebalance_amount < 0:
            action = f"Reduce by {inr(-r.rebalance_amount)}"
        else:
            action = "No action"
        with col.container(border=True):
            st.markdown(f"**{r.asset_class}**  \n"
                        f"<span style='color:{color}'>{icon}</span> {r.status}  \n"
                        f"{inr(r.value)} · {r.pct:.1f}%  \n"
                        f"<small>{action}"
                        + (f" · {inr(r.to_target_amount, signed=True)} to target" if not np.isnan(r.target) and r.status != "No recommendation" else "")
                        + "</small>", unsafe_allow_html=True)

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Equity share over time")
        eq_rng = status.set_index("asset_class").loc["Equity"]
        fig = go.Figure()
        fig.add_hrect(y0=eq_rng["low"], y1=eq_rng["high"], fillcolor=BAND, opacity=0.6, line_width=0,
                      annotation_text=f"Recommended {eq_rng['low']:.0f}–{eq_rng['high']:.0f}%",
                      annotation_position="bottom left", annotation_font=dict(size=11, color=MUTED))
        fig.add_scatter(x=eq["month"], y=eq["equity_pct"], mode="lines+markers", connectgaps=True,
                        name="Equity %", line=dict(color=CLASS_COLOR["Equity"], width=2),
                        marker=dict(size=7), hovertemplate="%{y:.2f}%")
        fig.update_yaxes(range=[30, 70], ticksuffix="%")
        show(style(fig, "", height=300, legend=False))

    with right:
        st.subheader("Strategy revisions")
        strat = d["strategy"].sort_values("revision")
        fig = go.Figure()
        for cls in m.ASSET_CLASSES:
            vals = strat[f"{cls}|Total"]
            if (vals == 0).all():
                continue
            fig.add_bar(y=strat["revision"].dt.strftime("%b %Y"), x=vals, name=cls, orientation="h",
                        marker=dict(color=CLASS_COLOR[cls], line=dict(width=2, color="#fcfcfb" if not DARK else "#1a1a19")),
                        text=vals.map("{:.0f}%".format), textposition="inside", insidetextanchor="middle",
                        hovertemplate=f"{cls}: %{{x:.0f}}%<extra></extra>")
        fig.update_layout(barmode="stack", hovermode="closest", legend_traceorder="normal")
        fig.update_xaxes(range=[0, 100], ticksuffix="%")
        show(style(fig, "", height=300))

    with st.expander("Strategy detail by sub-class"):
        detail = d["strategy"].sort_values("revision", ascending=False).copy()
        detail["revision"] = detail["revision"].dt.strftime("%b %Y")
        detail.columns = [c.replace("|", " · ") for c in detail.columns]
        st.dataframe(detail, hide_index=True)
