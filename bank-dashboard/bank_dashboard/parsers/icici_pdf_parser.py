import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber

from bank_dashboard.models import Transaction
from bank_dashboard.parsers.base_parser import BaseParser

_DATE_RE = re.compile(r'^\d{2}[-/]\d{2}[-/]\d{4}$')
_AMT_RE = re.compile(r'^[\d,]+\.\d{2}$')

# x-boundary: words at x < this are in the DATE column
_DATE_MAX_X = 70


def _to_decimal(s: str | None) -> Decimal | None:
    s = re.sub(r'[,\s]', '', (s or '').strip())
    try:
        return Decimal(s) if s else None
    except InvalidOperation:
        return None


def _parse_date(s: str):
    for fmt in ('%d-%m-%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _group_rows(words: list, tolerance: int = 4) -> dict:
    rows: dict = defaultdict(list)
    for w in words:
        key = round(w['top'] / tolerance) * tolerance
        rows[key].append(w)
    return {y: sorted(ws, key=lambda w: w['x0']) for y, ws in sorted(rows.items())}


class IciciPdfParser(BaseParser):
    """
    Parse ICICI Bank monthly PDF e-Statement.

    Uses word-position extraction instead of extract_tables() because ICICI
    PDFs use borderless table rows that pdfplumber cannot reconstruct as tables.
    Column positions are auto-detected from the DEPOSITS/WITHDRAWALS/BALANCE
    header row found on each page.
    """

    def parse(self, source: Path | str) -> list[Transaction]:
        all_words = []
        with pdfplumber.open(str(source)) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                for w in page.extract_words(x_tolerance=3, y_tolerance=3):
                    w = dict(w)
                    # Offset y per page so rows from different pages never collide
                    w['top'] = page_idx * 1000 + w['top']
                    all_words.append(w)
        return self._filter_by_date(self._extract(all_words))

    def _extract(self, all_words: list) -> list[Transaction]:
        rows = _group_rows(all_words)

        # col_bounds: (deposits_x, withdrawals_x, balance_x) — detected from header row
        col_bounds = None
        anchor_records: dict = {}   # y -> transaction data dict
        last_anchor_y = None

        for y, row_words in rows.items():
            row_text = ' '.join(w['text'].lower() for w in row_words)

            # ── Column header detection ───────────────────────────────────────
            if 'deposits' in row_text and 'withdrawals' in row_text and 'balance' in row_text:
                bounds = self._detect_col_bounds(row_words)
                if bounds:
                    col_bounds = bounds
                continue

            if col_bounds is None:
                continue

            dep_x, wd_x, bal_x = col_bounds
            mid_dep_wd = (dep_x + wd_x) / 2
            mid_wd_bal = (wd_x + bal_x) / 2

            # ── Stop description collection at section totals ─────────────────
            # "Total:" rows signal end of a transaction block; anything after is
            # TDS tables or footers that must not bleed into transaction descriptions.
            if 'total:' in row_text:
                last_anchor_y = None
                continue

            # ── Transaction anchor row (has a date in the DATE column) ────────
            date_words = [
                w for w in row_words
                if _DATE_RE.match(w['text']) and w['x0'] < _DATE_MAX_X
            ]

            if date_words:
                txn_date = _parse_date(date_words[0]['text'])
                if txn_date is None:
                    continue

                deposit = withdrawal = balance = None
                desc_parts = []

                for w in row_words:
                    x, text = w['x0'], w['text']
                    if x < _DATE_MAX_X:
                        continue  # date cell itself
                    if _AMT_RE.match(text):
                        val = _to_decimal(text)
                        if x < mid_dep_wd:
                            deposit = val
                        elif x < mid_wd_bal:
                            withdrawal = val
                        else:
                            balance = val
                    elif x < dep_x:  # MODE or PARTICULARS column
                        desc_parts.append(text)

                anchor_records[y] = {
                    'date': txn_date,
                    'deposit': deposit,
                    'withdrawal': withdrawal,
                    'balance': balance,
                    'desc': ' '.join(desc_parts),
                }
                last_anchor_y = y
                continue

            # ── Description continuation row ──────────────────────────────────
            if last_anchor_y is None:
                continue

            # Skip rows that have amounts in financial columns (totals/summaries)
            if any(_AMT_RE.match(w['text']) and w['x0'] >= dep_x for w in row_words):
                continue
            # Skip rows with words in the DATE column (section headers start at x≈31)
            if any(w['x0'] < _DATE_MAX_X for w in row_words):
                continue

            desc_words = [w for w in row_words if _DATE_MAX_X <= w['x0'] < dep_x]
            if desc_words:
                extra = ' '.join(w['text'] for w in desc_words)
                anchor_records[last_anchor_y]['desc'] += ' ' + extra

        # ── Build Transaction objects ─────────────────────────────────────────
        txns = []
        for rec in anchor_records.values():
            dep, wd = rec['deposit'], rec['withdrawal']
            if dep and dep > 0:
                tx_type, amount = 'credit', dep
            elif wd and wd > 0:
                tx_type, amount = 'debit', wd
            else:
                continue  # B/F or balance-only entry

            txns.append(Transaction(
                date=rec['date'],
                bank='ICICI',
                description=rec['desc'].strip(),
                amount=amount,
                type=tx_type,
                balance=rec['balance'],
                category='',
                source='pdf_statement',
            ))

        return txns

    def _detect_col_bounds(self, header_words: list):
        dep_x = wd_x = bal_x = None
        for w in header_words:
            t = w['text'].lower()
            if 'deposit' in t:
                dep_x = w['x0']
            elif 'withdrawal' in t:
                wd_x = w['x0']
            elif 'balance' in t:
                bal_x = w['x0']
        if dep_x and wd_x and bal_x:
            return dep_x, wd_x, bal_x
        return None
