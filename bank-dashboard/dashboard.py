"""
Streamlit Cashflow Dashboard
Run `python run.py` to fetch and parse e-Statements, then view this dashboard.
"""
import calendar
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from bank_dashboard.consolidator import compute_cashflow
from bank_dashboard.models import Transaction, load_transactions

CACHE_FILE = Path(__file__).parent / "data" / "transactions_cache.json"

st.set_page_config(
    page_title="Cashflow Dashboard",
    page_icon="₹",
    layout="wide",
)


@st.cache_data
def _load(cache_path: str) -> list[Transaction]:
    return load_transactions(cache_path)


def _to_df(transactions: list[Transaction]) -> pd.DataFrame:
    rows = [t.to_dict() for t in transactions]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].apply(lambda x: float(Decimal(x)))
    df["balance"] = df["balance"].apply(lambda x: float(Decimal(x)) if x else None)
    return df


# ── Load cached data ───────────────────────────────────────────────────────────
if not CACHE_FILE.exists():
    st.title("Cashflow Dashboard")
    st.info(
        "No data found. Run the pipeline to fetch your bank statements:\n\n"
        "```\npython run.py --month 3 --year 2026\n```"
    )
    st.stop()

transactions = _load(str(CACHE_FILE))

# ── Sidebar: Filter controls ───────────────────────────────────────────────────
st.sidebar.title("Filters")

all_dates = [t.date for t in transactions]
available_months = sorted({(d.year, d.month) for d in all_dates}, reverse=True)
month_labels = {(y, m): f"{calendar.month_name[m]} {y}" for y, m in available_months}

selected = st.sidebar.selectbox(
    "Month",
    options=list(month_labels.keys()),
    format_func=lambda k: month_labels[k],
)
sel_year, sel_month = selected

bank_options = sorted({t.bank for t in transactions})
selected_banks = st.sidebar.multiselect("Banks", options=bank_options, default=bank_options)

# ── Filter ─────────────────────────────────────────────────────────────────────
filtered = [
    t for t in transactions
    if t.date.year == sel_year and t.date.month == sel_month and t.bank in selected_banks
]
summary = compute_cashflow(filtered, sel_month, sel_year)

month_label = f"{calendar.month_name[sel_month]} {sel_year}"
st.title(f"Cashflow Dashboard — {month_label}")

if not filtered:
    st.warning("No transactions found for the selected filters.")
    st.stop()

df = _to_df(filtered)

# ── Row 1: KPI metrics ─────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
col1.metric("Total Income", f"₹{summary.total_income:,.2f}")
col2.metric("Total Expenses", f"₹{summary.total_expenses:,.2f}")
net = float(summary.net_cashflow)
col3.metric(
    "Net Cashflow",
    f"₹{summary.net_cashflow:,.2f}",
    delta=f"{'Surplus' if net >= 0 else 'Deficit'}",
    delta_color="normal" if net >= 0 else "inverse",
)

st.divider()

# ── Row 2: Charts ──────────────────────────────────────────────────────────────
col_pie, col_bar = st.columns(2)

with col_pie:
    st.subheader("Expenses by Category")
    expense_df = df[df["type"] == "debit"].groupby("category")["amount"].sum().reset_index()
    if not expense_df.empty:
        fig = px.pie(expense_df, values="amount", names="category", hole=0.3)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No expense data.")

with col_bar:
    st.subheader("Income vs Expenses by Bank")
    bar_rows = []
    for bank, vals in summary.by_bank.items():
        bar_rows.append({"bank": bank, "type": "Income", "amount": float(vals["income"])})
        bar_rows.append({"bank": bank, "type": "Expenses", "amount": float(vals["expenses"])})
    if bar_rows:
        bar_df = pd.DataFrame(bar_rows)
        fig = px.bar(bar_df, x="bank", y="amount", color="type", barmode="group",
                     color_discrete_map={"Income": "#2ecc71", "Expenses": "#e74c3c"})
        fig.update_layout(yaxis_title="Amount (₹)")
        st.plotly_chart(fig, use_container_width=True)

# ── Row 3: Daily running balance ───────────────────────────────────────────────
st.subheader("Daily Running Balance")
balance_df = df[df["balance"].notna()].copy()
if not balance_df.empty:
    balance_df = balance_df.sort_values("date")
    daily = balance_df.groupby(["date", "bank"])["balance"].last().reset_index()
    fig = px.line(daily, x="date", y="balance", color="bank", markers=True)
    fig.update_layout(yaxis_title="Balance (₹)", xaxis_title="Date")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No balance data available.")

# ── Row 4: Transaction table ───────────────────────────────────────────────────
st.subheader("Transactions")

display_df = df[["date", "bank", "description", "amount", "type", "category", "balance", "source"]].copy()
display_df["date"] = display_df["date"].dt.strftime("%d %b %Y")
display_df = display_df.sort_values("date", ascending=False)
display_df.columns = ["Date", "Bank", "Description", "Amount (₹)", "Type", "Category", "Balance (₹)", "Source"]


def _color_rows(row):
    color = "#d4edda" if row["Type"] == "credit" else "#f8d7da"
    return [f"background-color: {color}"] * len(row)


styled = display_df.style.apply(_color_rows, axis=1).format(
    {"Amount (₹)": "{:,.2f}", "Balance (₹)": lambda x: f"{x:,.2f}" if pd.notna(x) else "—"}
)
st.dataframe(styled, use_container_width=True, hide_index=True)

# ── Sidebar: download CSV ──────────────────────────────────────────────────────
csv = display_df.to_csv(index=False)
st.sidebar.download_button(
    label="Download CSV",
    data=csv,
    file_name=f"cashflow_{sel_year}_{sel_month:02d}.csv",
    mime="text/csv",
)
