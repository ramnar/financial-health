#!/usr/bin/env python3
"""
Cashflow Pipeline — fetch → parse → consolidate → cache → launch dashboard

Usage:
    python run.py                        # defaults to previous calendar month
    python run.py --month 3 --year 2025  # specific month
    python run.py --no-dashboard         # fetch and parse only, skip launching Streamlit
    python run.py --config /path/to/config.ini
"""
import argparse
import calendar
import shutil
import subprocess
import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parent))

from bank_dashboard import config as cfg_module
from bank_dashboard import categorizer, consolidator
from bank_dashboard.fetchers import gmail_fetcher, pdf_fetcher
from bank_dashboard.models import save_transactions
from bank_dashboard.parsers.equitas_pdf_parser import EquitasPdfParser
from bank_dashboard.parsers.icici_pdf_parser import IciciPdfParser


def main():
    parser = argparse.ArgumentParser(description="Bank cashflow pipeline")
    parser.add_argument("--month", type=int, help="Month number (1-12)")
    parser.add_argument("--year", type=int, help="4-digit year")
    parser.add_argument("--no-dashboard", action="store_true", help="Skip launching Streamlit")
    parser.add_argument("--config", default="config.ini", help="Path to config.ini")
    args = parser.parse_args()

    # ── Clear data folder ────────────────────────────────────────────────────
    data_dir = Path(__file__).parent / "data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
        print(f"Cleared data directory: {data_dir}")

    # ── Load config ──────────────────────────────────────────────────────────
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        print(f"  Copy config.ini.template to config.ini and fill in your credentials.")
        sys.exit(1)

    conf = cfg_module.load(args, str(config_path))
    month_name = calendar.month_name[conf.month]
    print(f"\n=== Cashflow Pipeline — {month_name} {conf.year} ===")
    print(f"  Date range: {conf.date_start} → {conf.date_end}\n")

    # ── Connect to Gmail ──────────────────────────────────────────────────────
    print("Connecting to Gmail via IMAP...")
    try:
        mail = gmail_fetcher.connect(conf.gmail_address, conf.gmail_app_password)
        print(f"  Connected as {conf.gmail_address}")
    except Exception as e:
        print(f"ERROR: Gmail connection failed: {e}")
        sys.exit(1)

    all_transactions = []

    # ── ICICI: fetch PDF statement ────────────────────────────────────────────
    print("\nFetching ICICI e-Statement PDF...")
    try:
        icici_pdfs = gmail_fetcher.fetch_icici_statement_pdfs(
            mail, conf.date_start, conf.date_end, conf.statements_dir
        )
        for pdf_path in icici_pdfs:
            print(f"  Decrypting {pdf_path.name}...")
            decrypted = conf.decrypted_dir / f"icici_decrypted_{pdf_path.name}"
            try:
                decrypted_path = pdf_fetcher.decrypt_pdf(pdf_path, conf.icici_pdf_password, decrypted)
                icici_pdf_parser = IciciPdfParser(conf.date_start, conf.date_end)
                pdf_txns = icici_pdf_parser.parse(decrypted_path)
                print(f"  Parsed {len(pdf_txns)} transactions from ICICI PDF")
                all_transactions.extend(pdf_txns)
            except Exception as e:
                print(f"  WARNING: ICICI PDF parse failed ({pdf_path.name}): {e}")
    except Exception as e:
        print(f"  WARNING: ICICI PDF fetch failed: {e}")

    # ── Equitas: fetch PDF statement ──────────────────────────────────────────
    print("\nFetching Equitas e-Statement PDF...")
    try:
        equitas_pdfs = gmail_fetcher.fetch_equitas_statement_pdfs(
            mail, conf.date_start, conf.date_end, conf.statements_dir
        )
        for pdf_path in equitas_pdfs:
            print(f"  Decrypting {pdf_path.name}...")
            decrypted = conf.decrypted_dir / f"equitas_decrypted_{pdf_path.name}"
            try:
                decrypted_path = pdf_fetcher.decrypt_pdf(pdf_path, conf.equitas_pdf_password, decrypted)
                equitas_parser = EquitasPdfParser(conf.date_start, conf.date_end)
                pdf_txns = equitas_parser.parse(decrypted_path)
                print(f"  Parsed {len(pdf_txns)} transactions from Equitas PDF")
                all_transactions.extend(pdf_txns)
            except Exception as e:
                print(f"  WARNING: Equitas PDF parse failed ({pdf_path.name}): {e}")
    except Exception as e:
        print(f"  WARNING: Equitas PDF fetch failed: {e}")

    mail.logout()

    if not all_transactions:
        print("\nNo transactions found. Check your Gmail credentials, date range, and email filters.")
        sys.exit(0)

    # ── Consolidate & categorize ──────────────────────────────────────────────
    print("\nConsolidating transactions...")
    transactions = consolidator.consolidate(all_transactions)
    for t in transactions:
        t.category = categorizer.categorize(t.description, t.type)
    print(f"  Total transactions after deduplication: {len(transactions)}")

    # ── Compute and print cashflow summary ────────────────────────────────────
    summary = consolidator.compute_cashflow(transactions, conf.month, conf.year)
    print(f"\n{'='*50}")
    print(f"  Cashflow Summary — {month_name} {conf.year}")
    print(f"{'='*50}")
    print(f"  Total Income:   ₹{summary.total_income:>12,.2f}")
    print(f"  Total Expenses: ₹{summary.total_expenses:>12,.2f}")
    print(f"  Net Cashflow:   ₹{summary.net_cashflow:>12,.2f}")
    print(f"\n  Expenses by Category:")
    for cat, amt in sorted(summary.by_category.items(), key=lambda x: -x[1]):
        print(f"    {cat:<18} ₹{amt:>10,.2f}")
    print(f"{'='*50}\n")

    # ── Cache to JSON ─────────────────────────────────────────────────────────
    save_transactions(transactions, conf.cache_file)
    print(f"Transactions cached to {conf.cache_file}")

    # ── Launch dashboard ──────────────────────────────────────────────────────
    if not args.no_dashboard:
        print("\nLaunching Streamlit dashboard...")
        dashboard_path = Path(__file__).parent / "dashboard.py"
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(dashboard_path)],
            check=False,
        )


if __name__ == "__main__":
    main()
