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


def _read_ini(path: Path) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    cfg.read(path, encoding="utf-8")
    return cfg


def load_targets(path: Path) -> pd.DataFrame:
    """Recommended range per asset class (only the asset-class sections of the file)."""
    cfg = _read_ini(path)
    rows = []
    for cls in ASSET_CLASSES:
        if cls not in cfg:
            continue
        low, high = cfg[cls].get("low", ""), cfg[cls].get("high", "")
        rows.append({"asset_class": cls,
                     "low": float(low) if low else np.nan,
                     "high": float(high) if high else np.nan})
    return pd.DataFrame(rows, columns=["asset_class", "low", "high"])


def load_settings(path: Path) -> dict:
    """CPI, financial-independence and emergency-fund settings from targets.ini."""
    cfg = _read_ini(path)
    cpi = cfg["CPI"] if "CPI" in cfg else {}
    fi = cfg["Financial Independence"] if "Financial Independence" in cfg else {}
    ef = cfg["Emergency Fund"] if "Emergency Fund" in cfg else {}

    def num(section, key, default=np.nan):
        value = section.get(key, "") if section else ""
        return float(value) if value.strip() else default

    return {
        "cpi_pct": num(cpi, "annual_inflation_pct"),
        "cpi_as_of": cpi.get("as_of", "") if cpi else "",
        "fi_target": num(fi, "target_amount"),
        "fi_real_return_pct": num(fi, "expected_real_return_pct", 8.0),
        "ef_assets": [a.strip() for a in (ef.get("assets", "") if ef else "").split(",") if a.strip()],
        "ef_min_months": num(ef, "minimum_months", 6.0),
    }


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


def invested_assets(asset_split: pd.DataFrame) -> float:
    """Portfolio value excluding 'Other' items such as a rent deposit."""
    tree = asset_tree(asset_split)
    return float(tree.loc[tree["asset_class"] != "Other", "value"].sum())


def months_to_target(start: float, monthly_saving: float, real_return_pct: float,
                     target: float, limit: int = 1200) -> int | None:
    """Months until start + monthly savings, compounding monthly, reach target. None if never."""
    value, months = start, 0
    growth = (1 + real_return_pct / 100) ** (1 / 12)
    while value < target:
        if months >= limit:
            return None
        value = value * growth + monthly_saving
        months += 1
    return months


def emergency_runway(asset_split: pd.DataFrame, assets: list[str],
                     avg_monthly_expense: float) -> tuple[float, float]:
    """Liquid amount (the named assets) and how many months of spending it covers."""
    a = asset_split[asset_split["level"] == "asset"]
    liquid = float(a.loc[a["name"].isin(assets), "value"].sum())
    return liquid, liquid / avg_monthly_expense if avg_monthly_expense else np.nan


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


def spending_movers(expense_heads: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """The n heads whose average monthly spend rose most and fell most vs the year before."""
    hi = head_inflation(expense_heads)
    latest = max(c for c in hi.columns if isinstance(c, (int, np.integer)))
    df = pd.DataFrame({"head": hi.index, "change": hi[latest] - hi[latest - 1],
                       "pct": hi["infl_1y"]}).reset_index(drop=True)
    up = df[df["change"] > 0].nlargest(n, "change")
    down = df[df["change"] < 0].nsmallest(n, "change")
    return pd.concat([up, down.iloc[::-1]], ignore_index=True)


def cash_flow_split(breakup: pd.DataFrame, cashflow: pd.DataFrame,
                    expense_heads: pd.DataFrame, top_n: int = 4) -> dict:
    """
    Income sources and where the money went, for the income-flow chart.

    Uses the last complete month when its head-wise breakup was captured; otherwise
    falls back to the latest year's head-wise totals (income as one total).
    """
    month = cashflow["month"].max()
    rows = breakup[breakup["month"] == month]
    if not rows.empty:
        income = rows[(rows["category"] == "Income") & (rows["amount"] > 0)]
        income = list(zip(income["head"], income["amount"]))
        expenses = rows[(rows["category"] == "Expense") & (rows["amount"] > 0)][["head", "amount"]]
        label = f"{month:%B %Y}"
    else:
        year = month.year
        income = [(f"Income {year}", float(cashflow.loc[cashflow["month"].dt.year == year, "income"].sum()))]
        y = expense_heads[(expense_heads["year"] == year) & (expense_heads["annual"] > 0)]
        expenses = y.rename(columns={"annual": "amount"})[["head", "amount"]]
        label = f"{year} so far (Jan–{month:%b})"

    expenses = expenses.sort_values("amount", ascending=False)
    top, rest = expenses.head(top_n), expenses.iloc[top_n:]
    out = list(zip(top["head"], top["amount"]))
    if not rest.empty:
        out.append((f"Other ({len(rest)} heads)", float(rest["amount"].sum())))
    total_in = sum(v for _, v in income)
    saved = total_in - expenses["amount"].sum()
    return {"label": label, "monthly": not rows.empty, "income": income,
            "expenses": out, "saved": saved, "total_income": total_in}


def action_items(status: pd.DataFrame, missing_months: list[str], expense_heads: pd.DataFrame,
                 last12: pd.DataFrame, runway_months: float, min_months: float,
                 fmt=lambda v: f"₹{v:,.0f}") -> list[dict]:
    """
    Flags for the Summary tab, most urgent first.
    Each item: {"level": critical|warning|info|good, "title": str, "detail": str}.
    """
    items = []
    if runway_months < min_months:
        items.append({"level": "critical", "title": f"Emergency fund covers {runway_months:.1f} months",
                      "detail": f"Below your {min_months:.0f}-month minimum"})
    for r in status.itertuples():
        if r.status in ("Below range", "Above range"):
            verb = "Add" if r.rebalance_amount > 0 else "Reduce by"
            items.append({"level": "warning",
                          "title": f"{r.asset_class} {r.pct:.1f}%, {r.status.lower()} {r.low:.0f}–{r.high:.0f}%",
                          "detail": f"{verb} {fmt(abs(r.rebalance_amount))} to get back in range"})
    if missing_months:
        items.append({"level": "warning", "title": "Portfolio not updated",
                      "detail": " and ".join([", ".join(missing_months[:-1]), missing_months[-1]]
                                             if len(missing_months) > 1 else missing_months)})
    # Heads with a big jump that also matter in rupees (≥ ₹1,000 a month now)
    hi = head_inflation(expense_heads)
    latest = max(c for c in hi.columns if isinstance(c, (int, np.integer)))
    jumps = hi[(hi["infl_1y"] >= 40) & (hi[latest] >= 1000)].nlargest(3, "infl_1y")
    if not jumps.empty:
        first, *others = list(jumps.itertuples())
        items.append({"level": "info", "title": f"{first.Index} up {first.infl_1y:.0f}% on last year",
                      "detail": ", ".join(f"{o.Index} +{o.infl_1y:.0f}%" for o in others) or "Average monthly spend"})
    below = last12[last12["savings"] < last12["savings_baseline"]]
    if not below.empty:
        items.append({"level": "info",
                      "title": f"Savings below baseline in {len(below)} of the last {len(last12)} months",
                      "detail": ", ".join(below["month"].dt.strftime("%b %Y"))})
    in_range = status.loc[status["status"] == "In range", "asset_class"].tolist()
    if in_range:
        items.append({"level": "good", "title": f"{', '.join(in_range)} in range", "detail": "No action needed"})
    if runway_months >= min_months:
        items.append({"level": "good", "title": f"Emergency fund covers {runway_months:.1f} months",
                      "detail": f"Above your {min_months:.0f}-month minimum"})
    return items


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
