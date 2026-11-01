"""
Generate synthetic data in the same shape as data/ (which holds real RR2FF data).

    python make_sample_data.py      # writes data_sample/*.csv

Numbers are random but internally consistent: assets roll up to their classes,
savings = income - expense, and head-wise annual totals match monthly expenses.
It also reproduces the quirks the dashboard handles: months with no portfolio
update (recorded as 0), a one-off bonus spike, and an incomplete current month.
"""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).parent / "data_sample"
rng = np.random.default_rng(42)

TODAY = date.today()
CURRENT = pd.Timestamp(TODAY.year, TODAY.month, 1)
START = pd.Timestamp(2022, 7, 1)
MONTHS = pd.date_range(START, CURRENT, freq="MS")

# Expense heads: (name, monthly base ₹, yearly growth, monthly noise, chance of a month with no spend)
EXPENSE_HEADS = [
    ("Rent", 22000, 0.05, 0.0, 0.0),
    ("SchoolFees", 14000, 0.12, 0.05, 0.0),
    ("Groceries", 8000, 0.10, 0.15, 0.0),
    ("Utilities", 2500, 0.06, 0.20, 0.0),
    ("PhoneInternet", 1500, 0.02, 0.10, 0.0),
    ("DiningOut", 2500, 0.08, 0.50, 0.1),
    ("Travel", 4000, 0.10, 0.90, 0.5),
    ("Medical", 1500, 0.05, 0.90, 0.3),
    ("HealthInsurance", 2200, 0.08, 0.0, 0.0),
    ("HouseholdHelp", 3000, 0.07, 0.05, 0.0),
    ("Shopping", 3000, 0.04, 0.70, 0.2),
    ("Entertainment", 1200, 0.03, 0.60, 0.3),
    ("GiftsDonations", 1500, 0.05, 0.90, 0.5),
    ("HomeRepairs", 1000, 0.05, 1.20, 0.6),
    ("Courses", 2000, 0.15, 1.00, 0.5),
    ("Miscellaneous", 2500, 0.05, 0.60, 0.1),
]

INCOME_HEADS = {"Salary": 0.78, "Bonus Provision": 0.10, "Provident Fund": 0.07,
                "NPS": 0.04, "Interest Income": 0.01}

# Asset -> (class, value at the latest month)
ASSETS = {
    "Stocks": ("Equity", 3_150_000),
    "MutualFunds": ("Equity", 3_480_000),
    "Retirement": ("Debt", 2_600_000),
    "Mutual Fund Debt": ("Debt", 1_250_000),
    "PPF": ("Debt", 420_000),
    "ExpenseFund": ("Debt", 150_000),
    "Gold": ("Commodities", 520_000),         # ~4.4%: deliberately below range
    "Cryptocurrency": ("Crypto", 60_000),
    "HouseRentAdvance": ("Other", 75_000),
}
CLASS_LABELS = {"Equity": "Equity Based Investments", "Debt": "Debt Based Investments",
                "Commodities": "Commodities", "Crypto": "Cryptocurrencies",
                "Other": "All Others"}


def cashflow_and_spending() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    years_in = np.array([(m - START).days / 365.25 for m in MONTHS])

    # Per-head monthly expenses
    rows = []
    for head, base, growth, noise, skip in EXPENSE_HEADS:
        for m, t in zip(MONTHS, years_in):
            amount = base * (1 + growth) ** t * max(0.0, 1 + noise * rng.standard_normal())
            if skip and rng.random() < skip:
                amount = 0.0
            if head == "SchoolFees" and m.month == 6:   # annual admission fee
                amount += base * 3
            rows.append({"month": m, "head": head, "amount": round(amount)})
    spend = pd.DataFrame(rows)

    expense = spend.groupby("month")["amount"].sum()
    income = pd.Series(
        [round(260_000 * 1.07 ** int(t) * (1 + 0.01 * rng.standard_normal())) for t in years_in],
        index=MONTHS)
    income[pd.Timestamp(2025, 3, 1)] += 650_000        # one-off bonus
    # RR2FF carries last month's figures into the current, unfinished month
    income[CURRENT], expense[CURRENT] = income.iloc[-2], expense.iloc[-2]
    spend.loc[spend["month"] == CURRENT, "amount"] = (
        spend.loc[spend["month"] == MONTHS[-2], "amount"].values)

    cf = pd.DataFrame({"month": MONTHS, "income": income.values.astype(float),
                       "expense": expense.values.astype(float)})
    cf["savings_reported"] = cf["income"] - cf["expense"]
    cf["savings_baseline"] = 190_000.0
    cf["savings"] = cf["income"] - cf["expense"]

    # Head-wise breakup for the last 12 complete months
    recent = MONTHS[-13:-1]
    exp_bk = spend[spend["month"].isin(recent) & (spend["amount"] > 0)].assign(category="Expense")
    inc_bk = pd.DataFrame([{"month": m, "head": h, "amount": round(income[m] * share),
                            "category": "Income"}
                           for m in recent for h, share in INCOME_HEADS.items()])
    breakup = pd.concat([inc_bk, exp_bk])[["month", "category", "head", "amount"]]

    # Annual totals per head (current year excludes the unfinished month)
    complete = spend[spend["month"] < CURRENT]
    annual = complete.groupby([complete["month"].dt.year.rename("year"), "head"])["amount"].sum()
    n_months = complete.groupby(complete["month"].dt.year)["month"].nunique()
    eh = annual.reset_index().rename(columns={"amount": "annual"})
    eh["monthly_avg"] = (eh["annual"] / eh["year"].map(n_months)).round()
    eh = eh[["head", "year", "annual", "monthly_avg"]].sort_values(["head", "year"], ascending=[True, False])

    return cf, breakup, eh


def portfolio() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    months = pd.date_range(CURRENT - pd.DateOffset(months=12), periods=12, freq="MS")
    latest = {cls: sum(v for c, v in ASSETS.values() if c == cls) for cls in CLASS_LABELS}

    # Walk each class backwards from today's value
    history = {}
    for cls, value in latest.items():
        drift = {"Equity": 0.012, "Debt": 0.006}.get(cls, 0.004)
        vol = {"Equity": 0.035, "Crypto": 0.10}.get(cls, 0.01)
        vals = [value]
        for _ in range(11):
            vals.append(vals[-1] / (1 + drift + vol * rng.standard_normal()))
        history[cls] = np.array(vals[::-1])
    total = sum(history.values())
    equity_pct = 100 * history["Equity"] / total

    nw = pd.DataFrame({"month": months, "assets": total.round(), "liabilities": 0.0})
    nw["planned_networth"] = np.linspace(total[0] * 0.95, total[0] * 0.95 * 1.09, 12).round()
    # Two months where no portfolio update was recorded
    missing = [7, 9]
    nw.loc[missing, "assets"] = 0.0
    nw["networth"] = nw["assets"] - nw["liabilities"]
    eq = pd.DataFrame({"month": months, "equity_pct": equity_pct.round(2)})
    eq.loc[missing, "equity_pct"] = 0.0

    split = pd.concat([
        pd.DataFrame([{"level": "asset", "name": n, "value": float(v)} for n, (_, v) in ASSETS.items()]),
        pd.DataFrame([{"level": "asset_class", "name": "Real Estate", "value": 0.0}]),
        pd.DataFrame([{"level": "asset_class", "name": CLASS_LABELS[c], "value": float(v)}
                      for c, v in latest.items()]),
    ], ignore_index=True)
    return nw, eq, split


def roi() -> pd.DataFrame:
    months = pd.date_range("2022-12-01", CURRENT, freq="MS")
    vals = 11 + np.cumsum(rng.normal(0.05, 0.6, len(months)))
    df = pd.DataFrame({"month": months, "roi_pct": vals.clip(6, 20).round(2)})
    # RR2FF only records ROI when the portfolio is updated
    return df[rng.random(len(df)) > 0.3].reset_index(drop=True)


def strategy() -> pd.DataFrame:
    rows = [
        ("2023-01-01", (8, 14, 24, 4), (6, 0), (0, 0), (0, 0), 44),
        ("2024-04-01", (6, 12, 22, 5), (7, 0), (0, 0), (1, 0), 47),
        ("2025-03-01", (7, 13, 25, 5), (8, 0), (0, 0), (2, 0), 40),
    ]
    out = []
    for rev, eq, com, re_, cr, debt in rows:
        out.append({
            "revision": rev,
            "Equity|Small-Cap": eq[0], "Equity|Mid-Cap": eq[1], "Equity|Large-Cap": eq[2],
            "Equity|Intn'l": eq[3], "Equity|Total": sum(eq),
            "Commodities|Gold": com[0], "Commodities|Silver": com[1], "Commodities|Total": sum(com),
            "Real Estate|Res.": re_[0], "Real Estate|Comm.": re_[1], "Real Estate|Total": sum(re_),
            "Crypto|Bitcoin": cr[0], "Crypto|Others": cr[1], "Crypto|Total": sum(cr),
            "Debt|All Debt": debt, "Debt|Total": debt,
        })
    df = pd.DataFrame(out).astype({c: float for c in out[0] if c != "revision"})
    assert (df.filter(like="|Total").sum(axis=1) == 100).all()
    return df


def main() -> None:
    OUT.mkdir(exist_ok=True)
    cf, breakup, eh = cashflow_and_spending()
    nw, eq, split = portfolio()
    outputs = {"cashflow": cf, "breakup": breakup, "expense_heads": eh, "networth": nw,
               "equity_pct": eq, "asset_split": split, "roi": roi(), "strategy": strategy()}
    for name, df in outputs.items():
        df.to_csv(OUT / f"{name}.csv", index=False)
        print(f"{name:14s} {len(df):4d} rows -> data_sample/{name}.csv")


if __name__ == "__main__":
    main()
