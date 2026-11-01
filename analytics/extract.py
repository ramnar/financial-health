"""
Extract RR2FF analytics data from captured HTML pages into tidy CSVs.

    python capture_rr2ff.py   # saves pages into raw/
    python extract.py         # raw/*.html  ->  data/*.csv

Every series is monthly and keyed by `month` (first day of the month, ISO date).
"""
import json
import re
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
RAW = ROOT / "raw"
DATA = ROOT / "data"


def _html(name: str) -> str:
    return (RAW / name).read_text(encoding="utf-8")


def _month(label: str) -> pd.Timestamp:
    """'Nov-2025' or 'Nov 2025' -> 2025-11-01."""
    return pd.to_datetime(label.replace(" ", "-"), format="%b-%Y")


def _add_rows_blocks(html: str) -> list[list[list]]:
    """Every Google Charts `addRows([...])` literal on the page, in order."""
    blocks = []
    for body in re.findall(r"addRows\(\[(.*?)\]\);", html, re.S):
        rows = []
        for row in re.findall(r"\[([^\[\]]*)\]", body):
            cells = [c.strip().strip("'\"") for c in row.split(",")]
            rows.append(cells)
        blocks.append(rows)
    return blocks


def _array_tables(html: str) -> list[list[list]]:
    """Every `arrayToDataTable([...])` literal, header row dropped."""
    tables = []
    for body in re.findall(r"arrayToDataTable\(\[(.*?)\]\);", html, re.S):
        rows = [[c.strip().strip("'\"") for c in r.rsplit(",", 1)]
                for r in re.findall(r"\[([^\[\]]*)\]", body)]
        tables.append(rows[1:])
    return tables


def _num(cell: str) -> float | None:
    return None if cell in ("null", "") else float(cell)


# ── Portfolio ─────────────────────────────────────────────────────────────────

def networth() -> pd.DataFrame:
    assets, liabilities, planned = _add_rows_blocks(_html("01_networthtrend.html"))
    df = pd.DataFrame({
        "month": [_month(r[0]) for r in assets],
        "assets": [_num(r[1]) for r in assets],
        "liabilities": [_num(r[1]) for r in liabilities],
        "planned_networth": [_num(r[1]) for r in planned],
    })
    df["networth"] = df["assets"] - df["liabilities"]
    return df


def equity_pct() -> pd.DataFrame:
    rows = _add_rows_blocks(_html("02_portfoliobalancetrend.html"))[0]
    return pd.DataFrame({"month": [_month(r[0]) for r in rows],
                         "equity_pct": [_num(r[1]) for r in rows]})


def roi() -> pd.DataFrame:
    rows = [r for r in _add_rows_blocks(_html("03_roitrend.html"))[0] if r[0]]
    return pd.DataFrame({"month": [_month(r[0]) for r in rows],
                         "roi_pct": [_num(r[1]) for r in rows]})


def asset_split() -> pd.DataFrame:
    by_asset, by_class = _array_tables(_html("09_assetwisesplit.html"))
    a = pd.DataFrame(by_asset, columns=["name", "value"]).assign(level="asset")
    c = pd.DataFrame(by_class, columns=["name", "value"]).assign(level="asset_class")
    df = pd.concat([a, c], ignore_index=True)
    df["value"] = df["value"].astype(float)
    df["name"] = df["name"].str.rstrip("*")  # RR2FF marks grouped assets with '*'
    return df[["level", "name", "value"]]


def strategy() -> pd.DataFrame:
    """Target allocation history: one row per revision, one column per sub-class."""
    tables = pd.read_html(StringIO(_html("10_balancing_strategy.html")))
    t = tables[-1]
    sub = t.iloc[0].tolist()                      # second header row
    groups = [c.split(".")[0] for c in t.columns]  # first header row
    cols = ["revision"] + [f"{g}|{s}" for g, s in zip(groups[1:], sub[1:])]
    body = t.iloc[1:].copy()
    body.columns = cols
    body = body.loc[:, ~body.columns.str.endswith("|nan")]
    out = pd.DataFrame({"revision": pd.to_datetime(body["revision"], format="%b %Y")})
    for c in body.columns[1:]:
        out[c] = body[c].astype(str).str.rstrip("%").astype(float)
    return out.sort_values("revision").reset_index(drop=True)


# ── Cash flow ─────────────────────────────────────────────────────────────────

def cashflow() -> pd.DataFrame:
    def ym_series(name: str, col: str) -> pd.DataFrame:
        raw = re.search(r"var chartRows = (\[.*?\]);", _html(name), re.S).group(1)
        rows = [tuple(int(x) for x in r) for r in re.findall(r"\[(\d+),(\d+),(-?\d+)\]", raw)]
        return pd.DataFrame({"month": [pd.Timestamp(y, m + 1, 1) for y, m, _ in rows],
                             col: [float(v) for *_, v in rows]})

    income = ym_series("04_income_trend.html", "income")
    expense = ym_series("05_expense_trend.html", "expense")

    raw = re.search(r"var chartRows = (\[.*?\]);", _html("06_savingstrend.html"), re.S).group(1)
    sav = pd.DataFrame(json.loads(raw), columns=["label", "savings_reported", "savings_baseline"])
    sav["month"] = sav["label"].map(_month)

    df = income.merge(expense, on="month", how="outer").merge(
        sav.drop(columns="label"), on="month", how="outer")
    df = df.sort_values("month").reset_index(drop=True)
    df["savings"] = df["income"].fillna(0) - df["expense"].fillna(0)
    return df


def breakups() -> pd.DataFrame:
    """Income & expense head-wise split for every captured month."""
    frames = []
    for path in sorted(RAW.glob("07_headwisebreakup*.html")):
        html = path.read_text(encoding="utf-8")
        mon, yr = re.search(r"\((\w{3}) - (\d{4})\)", re.sub(r"<[^>]+>", "", html)).groups()
        income, expense = _array_tables(html)
        for kind, rows in (("Income", income), ("Expense", expense)):
            f = pd.DataFrame(rows, columns=["head", "amount"])
            f["amount"] = f["amount"].astype(float)
            frames.append(f.assign(month=_month(f"{mon}-{yr}"), category=kind))
    df = pd.concat(frames, ignore_index=True).drop_duplicates(["month", "category", "head"])
    return df[["month", "category", "head", "amount"]]


def expense_heads() -> pd.DataFrame:
    """Annual expense per head (long format): head, year, annual, monthly_avg."""
    t = pd.read_html(StringIO(_html("08_headwiseinflation.html")))[0]
    years = [int(y) for y in t.iloc[0, 1:6]]
    body = t.iloc[1:].rename(columns={t.columns[0]: "head"})
    body = body[~body["head"].str.startswith("Year Total")]
    rows = []
    for _, r in body.iterrows():
        for i, year in enumerate(years, start=1):
            m = re.match(r"([\d,]+)\s*\(([\d,]+)\)", str(r.iloc[i]))
            annual, avg = (float(g.replace(",", "")) for g in m.groups())
            rows.append({"head": r["head"], "year": year, "annual": annual, "monthly_avg": avg})
    return pd.DataFrame(rows)


def main() -> None:
    DATA.mkdir(exist_ok=True)
    outputs = {
        "networth": networth(),
        "equity_pct": equity_pct(),
        "roi": roi(),
        "asset_split": asset_split(),
        "strategy": strategy(),
        "cashflow": cashflow(),
        "breakup": breakups(),
        "expense_heads": expense_heads(),
    }
    for name, df in outputs.items():
        df.to_csv(DATA / f"{name}.csv", index=False)
        print(f"{name:14s} {len(df):4d} rows -> data/{name}.csv")


if __name__ == "__main__":
    main()
