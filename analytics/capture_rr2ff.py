"""
One-off capture of RR2FF analytics pages.

Opens a visible browser at the login page. Log in manually, then create the
flag file (analytics/raw/.logged_in) to start capturing. Each page is saved
as a full-page PNG and its HTML into analytics/raw/.
"""
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://www.manoj-arora.a2hosted.com/cgi-bin/RR2FFv2/"
PAGES = {
    "01_networthtrend": "analytics_networthtrend.cgi?username=ramnar",
    "02_portfoliobalancetrend": "analytics_portfoliobalancetrend.cgi?username=ramnar",
    "03_roitrend": "analytics_roitrend.cgi?username=ramnar&Category=Portfolio&HeadID=0",
    "04_income_trend": "analytics_categorywise_trend.cgi?username=ramnar&category=Income&filter=inception",
    "05_expense_trend": "analytics_categorywise_trend.cgi?username=ramnar&category=Expense&filter=inception",
    "06_savingstrend": "analytics_savingstrend.cgi?username=ramnar&filter=inception",
    "07_headwisebreakup": "analytics_headwisebreakup.cgi?username=ramnar&Category=Expense&month=Feb&year=2024",
    "08_headwiseinflation": "analytics_headwiseinflation.cgi?username=ramnar",
    "09_assetwisesplit": "analytics_assetwisesplit.cgi?username=ramnar",
    "10_balancing_strategy": "portfolio_balancing_strategy.cgi?username=ramnar",
    "11_balance_status": "portfolio_balance_status.cgi?username=ramnar",
}

OUT = Path(__file__).parent / "raw"
FLAG = OUT / ".logged_in"


def capture(page, name: str, url: str, screenshot: bool = True) -> None:
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(2000)  # let charts finish rendering
    if screenshot:
        page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    (OUT / f"{name}.html").write_text(page.content(), encoding="utf-8")
    print(f"captured {name}", flush=True)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    FLAG.unlink(missing_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto("https://www.manoj-arora.a2hosted.com/")
        print("Waiting for login...", flush=True)
        while not FLAG.exists():
            time.sleep(1)

        for name, path in PAGES.items():
            capture(page, name, BASE + path)

        # The breakup page shows one month; follow its month links to get them all
        page.goto(BASE + PAGES["07_headwisebreakup"], wait_until="networkidle")
        links = page.eval_on_selector_all(
            "a[href*='analytics_headwisebreakup']", "els => els.map(e => e.href)")
        for url in dict.fromkeys(links):
            month, year = re.search(r"month=(\w+)&year=(\d+)", url).groups()
            capture(page, f"07_headwisebreakup_{year}_{month}", url, screenshot=False)

        browser.close()
    FLAG.unlink(missing_ok=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
