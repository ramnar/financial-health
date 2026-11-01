# Portfolio Analytics

A Streamlit + Plotly dashboard rebuilt from the RR2FF analytics pages (net worth,
ROI, income/expense/savings trends, head-wise spending and inflation, asset split,
and rebalancing status).

## Refreshing the data

```bash
cd analytics
pip install -r requirements.txt && playwright install chromium

python capture_rr2ff.py      # opens a browser at the RR2FF login page
# log in, then in another terminal:
touch raw/.logged_in         # starts the capture; pages are saved into raw/

python extract.py            # raw/*.html -> data/*.csv
streamlit run app.py
```

`raw/` and `data/` hold personal financial data and are git-ignored.

## Files

| File | Purpose |
|---|---|
| `capture_rr2ff.py` | Saves each RR2FF analytics page (HTML + screenshot) after a manual login |
| `extract.py` | Pulls the chart data and tables out of the saved pages into tidy CSVs |
| `targets.ini` | Recommended allocation ranges (the balance-status page loads these in iframes, so they're kept by hand) |
| `metrics.py` | All calculations: missing-month handling, trends, inflation, rebalancing |
| `app.py` | The dashboard |
| `test_metrics.py` | `python -m unittest test_metrics` — includes checks that the extracted data reproduces RR2FF's own figures |

## Data notes

- RR2FF records `0` for months with no portfolio update; these are treated as missing.
- The current calendar month is excluded from cash-flow charts as incomplete.
- Head-wise inflation follows RR2FF's definition: change in average monthly spend
  divided by the number of years (not compounded).
