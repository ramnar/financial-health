import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from bank_dashboard.models import Transaction
from bank_dashboard.parsers.base_parser import BaseParser

_RE_AMOUNT = re.compile(r"INR\s*([\d,]+\.?\d*)", re.I)

# "on Apr 27, 2026 at 12:46" or "on 27-Apr-2026"
_RE_DATE_LONG = re.compile(r"\bon\s+(\w+\s+\d{1,2},\s+\d{4})", re.I)
_RE_DATE_SHORT = re.compile(r"\bon\s+(\d{2}-\w{3}-\d{4})", re.I)

# Debit patterns: "made an online payment", "debited", "withdrawn"
_RE_DEBIT = re.compile(
    r"made an online payment|debited|withdrawn|deducted|paid|purchase", re.I
)
# Credit patterns: "credited|deposited|received|refund"
_RE_CREDIT = re.compile(r"credited|deposited|received|refund", re.I)

# Description: "towards <merchant> from your" or "Info: <text>" or "for <text>"
_RE_TOWARDS = re.compile(r"towards\s+(.+?)\s+from your", re.I | re.S)
_RE_INFO = re.compile(r"Info[:\s]+(.+)", re.I)

_DATE_FORMATS = ["%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%d-%B-%Y"]


def _clean_amount(s: str) -> Decimal:
    return Decimal(s.replace(",", ""))


def _parse_date(body: str) -> datetime | None:
    for pattern in (_RE_DATE_LONG, _RE_DATE_SHORT):
        m = pattern.search(body)
        if m:
            date_str = re.sub(r"\s+", " ", m.group(1).strip())
            for fmt in _DATE_FORMATS:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
    return None


class IciciEmailParser(BaseParser):
    """Parse ICICI Bank transaction alert email bodies."""

    def parse(self, source: Path | str) -> list[Transaction]:
        raise NotImplementedError("Use parse_bodies() for email text.")

    def parse_bodies(self, bodies: list[str]) -> list[Transaction]:
        txns = []
        for body in bodies:
            txn = self._parse_body(body)
            if txn and self._in_range(txn.date):
                txns.append(txn)
        return txns

    def _parse_body(self, body: str) -> Transaction | None:
        # Strip excessive whitespace for cleaner matching
        body_clean = re.sub(r"\s+", " ", body).strip()

        # Amount
        amount_match = _RE_AMOUNT.search(body_clean)
        if not amount_match:
            return None
        try:
            amount = _clean_amount(amount_match.group(1))
        except InvalidOperation:
            return None
        if amount <= 0:
            return None

        # Date
        dt = _parse_date(body_clean)
        if not dt:
            return None
        txn_date = dt.date()

        # Credit/debit
        if _RE_CREDIT.search(body_clean):
            tx_type = "credit"
        else:
            tx_type = "debit"

        # Description
        towards_match = _RE_TOWARDS.search(body_clean)
        if towards_match:
            description = re.sub(r"\s+", " ", towards_match.group(1)).strip()
        else:
            info_match = _RE_INFO.search(body_clean)
            description = info_match.group(1).strip() if info_match else body_clean[:80]

        return Transaction(
            date=txn_date,
            bank="ICICI",
            description=description,
            amount=amount,
            type=tx_type,
            balance=None,
            category="",
            source="email_alert",
        )
