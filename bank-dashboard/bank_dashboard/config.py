import argparse
import calendar
import configparser
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path


@dataclass
class Config:
    gmail_address: str
    gmail_app_password: str
    month: int
    year: int
    date_start: date
    date_end: date
    icici_pdf_password: str
    equitas_pdf_password: str
    statements_dir: Path
    decrypted_dir: Path
    cache_file: Path


def _parse_month(s: str) -> int:
    """Accept month number (3) or name (March / mar)."""
    s = s.strip()
    if s.isdigit():
        return int(s)
    import calendar
    s_lower = s.lower()
    for i, name in enumerate(calendar.month_name):
        if name.lower().startswith(s_lower[:3]):
            return i
    raise ValueError(f"Cannot parse month: {s!r}")


def _prev_month() -> tuple[int, int]:
    today = date.today()
    first_of_this = today.replace(day=1)
    last_prev = first_of_this - timedelta(days=1)
    return last_prev.month, last_prev.year


def get_date_range(month: int, year: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def load(args: argparse.Namespace | None = None, config_path: str = "config.ini") -> Config:
    ini = configparser.ConfigParser()
    ini.read(config_path)

    def _get(section, key, env_var=None, fallback=None):
        if env_var and os.environ.get(env_var):
            return os.environ[env_var]
        return ini.get(section, key, fallback=fallback or "")

    gmail_address = _get("gmail", "gmail_address", "GMAIL_ADDRESS")
    gmail_app_password = _get("gmail", "gmail_app_password", "GMAIL_APP_PASSWORD")

    # Month/year: CLI args > env vars > config.ini > default (previous month)
    month_str = None
    year_str = None
    if args and getattr(args, "month", None):
        month_str = str(args.month)
    if args and getattr(args, "year", None):
        year_str = str(args.year)

    if not month_str:
        month_str = _get("period", "month", "DASHBOARD_MONTH") or None
    if not year_str:
        year_str = _get("period", "year", "DASHBOARD_YEAR") or None

    if month_str and year_str:
        month = _parse_month(month_str)
        year = int(year_str)
    else:
        month, year = _prev_month()

    date_start, date_end = get_date_range(month, year)

    base = Path(config_path).parent

    def _path(section, key, default):
        raw = _get(section, key, fallback=default)
        p = Path(raw)
        return p if p.is_absolute() else base / p

    return Config(
        gmail_address=gmail_address,
        gmail_app_password=gmail_app_password,
        month=month,
        year=year,
        date_start=date_start,
        date_end=date_end,
        icici_pdf_password=_get("passwords", "icici_pdf_password", "ICICI_PDF_PASSWORD"),
        equitas_pdf_password=_get("passwords", "equitas_pdf_password", "EQUITAS_PDF_PASSWORD"),
        statements_dir=_path("paths", "statements_dir", "./data/statements"),
        decrypted_dir=_path("paths", "decrypted_dir", "./data/decrypted"),
        cache_file=_path("paths", "cache_file", "./data/transactions_cache.json"),
    )
