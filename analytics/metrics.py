"""Pure calculations behind the dashboard. No Streamlit or Plotly in here."""
import configparser
from pathlib import Path

import numpy as np
import pandas as pd

ASSET_CLASSES = ["Equity", "Debt", "Commodities", "Crypto", "Real Estate"]

# RR2FF asset-class labels -> the short names used on the strategy page
CLASS_ALIASES = {
    "Equity Based Investments": "Equity",
    "Debt Based Investments": "Debt",
    "Commodities": "Commodities",
    "Cryptocurrencies": "Crypto",
    "Real Estate": "Real Estate",
    "Life Insurance": "Other",
    "All Others": "Other",
}

# Which class each asset rolls up into (verified: the sums match RR2FF's class totals)
ASSET_TO_CLASS = {
    "Stocks": "Equity",
    "MutualFunds": "Equity",
    "Retirement": "Debt",
    "Mutual Fund Debt": "Debt",
    "PPF": "Debt",
    "ExpenseFund": "Debt",
    "Gold": "Commodities",
    "Cryptocurrency": "Crypto",
    "HouseRentAdvance": "Other",
    "Miscellaneous": "Other",
    "All Others": "Other",
}

PERIOD_MONTHS = {"1Y": 12, "2Y": 24, "3Y": 36, "All": None}


# ── Loading ───────────────────────────────────────────────────────────────────

def load_data(data_dir: Path) -> dict[str, pd.DataFrame]:
    dated = {"networth": "month", "equity_pct": "month", "roi": "month",
             "cashflow": "month", "breakup": "month", "strategy": "revision"}
    out = {}
    for path in data_dir.glob("*.csv"):
        date_col = dated.get(path.stem)
        out[path.stem] = pd.read_csv(path, parse_dates=[date_col] if date_col else None)
    return out


def load_targets(path: Path) -> pd.DataFrame:
    cfg = configparser.ConfigParser()
    cfg.read(path)
    rows = []
    for cls in cfg.sections():
        low, high = cfg[cls].get("low", ""), cfg[cls].get("high", "")
        rows.append({"asset_class": cls,
                     "low": float(low) if low else np.nan,
                     "high": float(high) if high else np.nan})
    return pd.DataFrame(rows)


# ── Portfolio ─────────────────────────────────────────────────────────────────

def mark_missing(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """RR2FF writes 0 for months with no portfolio update; treat those as missing."""
    out = df.copy()
    out[cols] = out[cols].replace(0, np.nan)
    return out


def latest_change(series: pd.Series) -> tuple[float, float | None]:
    """Latest non-missing value and its change from the previous non-missing value."""
    s = series.dropna()
    if s.empty:
        return np.nan, None
    return s.iloc[-1], (s.iloc[-1] - s.iloc[-2]) if len(s) > 1 else None


def class_allocation(asset_split: pd.DataFrame) -> pd.DataFrame:
    """Value and % of portfolio per asset class, in ASSET_CLASSES order (+ Other)."""
    c = asset_split[asset_split["level"] == "asset_class"].copy()
    c["asset_class"] = c["name"].map(CLASS_ALIASES).fillna("Other")
    c = c.groupby("asset_class", as_index=False)["value"].sum()
    c["pct"] = 100 * c["value"] / c["value"].sum()
    order = {name: i for i, name in enumerate(ASSET_CLASSES + ["Other"])}
    return c.sort_values("asset_class", key=lambda s: s.map(order)).reset_index(drop=True)


def asset_tree(asset_split: pd.DataFrame) -> pd.DataFrame:
    """Non-zero assets with their parent class, for a treemap."""
    a = asset_split[(asset_split["level"] == "asset") & (asset_split["value"] > 0)].copy()
    a["asset_class"] = a["name"].map(ASSET_TO_CLASS).fillna("Other")
    return a[["asset_class", "name", "value"]].reset_index(drop=True)


def latest_targets(strategy: pd.DataFrame) -> dict[str, float]:
    last = strategy.sort_values("revision").iloc[-1]
    return {cls: last[f"{cls}|Total"] for cls in ASSET_CLASSES}


def balance_status(alloc: pd.DataFrame, ranges: pd.DataFrame,
                   targets: dict[str, float]) -> pd.DataFrame:
    """Actual vs recommended range per class, and the ₹ needed to get back in range."""
    total = alloc["value"].sum()
    df = (pd.DataFrame({"asset_class": ASSET_CLASSES})
          .merge(alloc, on="asset_class", how="left")
          .merge(ranges, on="asset_class", how="left")
          .fillna({"value": 0.0, "pct": 0.0}))
    df["target"] = df["asset_class"].map(targets)

    def status(r):
        if np.isnan(r.low) or np.isnan(r.high):
            return "No recommendation"
        if r.pct < r.low:
            return "Below range"
        if r.pct > r.high:
            return "Above range"
        return "In range"

    df["status"] = df.apply(status, axis=1)
    # Positive = invest more, negative = reduce. Zero when already inside the range.
    gap_pct = np.where(df["pct"] < df["low"], df["low"] - df["pct"],
                       np.where(df["pct"] > df["high"], df["high"] - df["pct"], 0.0))
    df["rebalance_amount"] = np.nan_to_num(gap_pct) * total / 100
    df["to_target_amount"] = (df["target"] - df["pct"]) * total / 100
    return df


# ── Cash flow ─────────────────────────────────────────────────────────────────

def complete_months(cashflow: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    """Drop the current (unfinished) month and months missing income or expense."""
    current = pd.Timestamp(today.year, today.month, 1)
    cf = cashflow[(cashflow["month"] < current)].dropna(subset=["income", "expense"])
    cf = cf.copy()
    cf["savings_rate"] = 100 * cf["savings"] / cf["income"]
    return cf.reset_index(drop=True)


def filter_period(df: pd.DataFrame, period: str, col: str = "month") -> pd.DataFrame:
    n = PERIOD_MONTHS[period]
    if n is None:
        return df
    start = df[col].max() - pd.DateOffset(months=n - 1)
    return df[df[col] >= start]


def rolling_mean(series: pd.Series, window: int = 6) -> pd.Series:
    return series.rolling(window, min_periods=window).mean()


def annual_trend(df: pd.DataFrame, col: str) -> float:
    """Slope of a least-squares line through the monthly values, in ₹ per year."""
    s = df[["month", col]].dropna()
    if len(s) < 2:
        return np.nan
    x = (s["month"].dt.year * 12 + s["month"].dt.month).to_numpy(dtype=float)
    return float(np.polyfit(x, s[col].to_numpy(dtype=float), 1)[0] * 12)


def trailing_summary(cf: pd.DataFrame, months: int = 12) -> dict[str, float]:
    last = cf.tail(months)
    income, expense = last["income"].sum(), last["expense"].sum()
    return {"income": income, "expense": expense, "savings": income - expense,
            "savings_rate": 100 * (income - expense) / income if income else np.nan,
            "avg_expense": last["expense"].mean()}


# ── Spending ──────────────────────────────────────────────────────────────────

def head_inflation(expense_heads: pd.DataFrame) -> pd.DataFrame:
    """
    Per-head monthly-average spend by year, plus 1/2/3-year inflation.

    Matches RR2FF's definition: inflation over N years is the total change in
    monthly-average spend divided by N (not compounded), so a partial current
    year compares fairly with full past years. Undefined when the base is 0.
    """
    wide = expense_heads.pivot(index="head", columns="year", values="monthly_avg")
    wide = wide[sorted(wide.columns)]
    latest = wide.columns[-1]
    out = wide.copy()
    for n in (1, 2, 3):
        base = wide[latest - n]
        out[f"infl_{n}y"] = np.where(base > 0, 100 * (wide[latest] / base - 1) / n, np.nan)
    return out


def total_inflation(expense_heads: pd.DataFrame) -> pd.Series:
    """Same calculation on the household total ('Year Total' row on RR2FF)."""
    totals = expense_heads.groupby("year")[["annual", "monthly_avg"]].sum()
    latest = totals.index.max()
    return pd.Series({f"infl_{n}y": 100 * (totals.loc[latest, "monthly_avg"]
                                           / totals.loc[latest - n, "monthly_avg"] - 1) / n
                      for n in (1, 2, 3)})


def top_heads(expense_heads: pd.DataFrame, year: int, n: int = 12) -> pd.DataFrame:
    """Top-n heads by annual spend in `year`, the rest folded into 'Everything else'."""
    y = expense_heads[expense_heads["year"] == year].sort_values("annual", ascending=False)
    y = y[y["annual"] > 0]
    top, rest = y.head(n), y.iloc[n:]
    if not rest.empty:
        top = pd.concat([top, pd.DataFrame([{
            "head": f"Everything else ({len(rest)} heads)", "year": year,
            "annual": rest["annual"].sum(), "monthly_avg": rest["monthly_avg"].sum()}])])
    return top.reset_index(drop=True)
