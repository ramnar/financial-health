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

# Transaction date column: x < this value (value date column is at x ≈ 111)
_TXN_DATE_MAX_X = 100
# Narration column starts at x ≈ 245
_NARRATION_MIN_X = 240


def _to_decimal(s: str | None) -> Decimal | None:
    s = re.sub(r'[,\s]', '', (s or '').strip())
    try:
        return Decimal(s) if s else None
    except InvalidOperation:
        return None


def _parse_date(s: str):
    for fmt in ('%d/%m/%Y', '%d-%m-%Y'):
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


class EquitasPdfParser(BaseParser):
    """
    Parse Equitas Small Finance Bank PDF e-Statement.

    Uses word-position extraction instead of extract_tables() because Equitas
    PDFs use borderless table rows. Columns are auto-detected from the
    Debit/Credit/Balance header row found on each page.

    Equitas has two date columns per row: Transaction Date (x≈44) and
    Value Date (x≈111). Only the Transaction Date is used as the anchor.
    """

    def parse(self, source: Path | str) -> list[Transaction]:
        all_words = []
        with pdfplumber.open(str(source)) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                for w in page.extract_words(x_tolerance=3, y_tolerance=3):
                    w = dict(w)
                    w['top'] = page_idx * 1000 + w['top']
                    all_words.append(w)
        return self._filter_by_date(self._extract(all_words))

    def _extract(self, all_words: list) -> list[Transaction]:
        rows = _group_rows(all_words)

        # col_bounds: (debit_x, credit_x, balance_x)
        col_bounds = None
        anchor_records: dict = {}
        last_anchor_y = None

        for y, row_words in rows.items():
            row_text = ' '.join(w['text'].lower() for w in row_words)

            # ── Column header detection ───────────────────────────────────────
            # The Equitas header row contains "debit", "credit", and "balance"
            if 'debit' in row_text and 'credit' in row_text and 'balance' in row_text:
                bounds = self._detect_col_bounds(row_words)
                if bounds:
                    col_bounds = bounds
                continue

            if col_bounds is None:
                continue

            deb_x, cr_x, bal_x = col_bounds
            mid_deb_cr = (deb_x + cr_x) / 2
            mid_cr_bal = (cr_x + bal_x) / 2

            # ── Stop description collection at section totals ─────────────────
            if 'total:' in row_text or 'closing balance' in row_text:
                last_anchor_y = None
                continue

            # ── Transaction anchor row (has a date in the TXN DATE column) ───
            date_words = [
                w for w in row_words
                if _DATE_RE.match(w['text']) and w['x0'] < _TXN_DATE_MAX_X
            ]

            if date_words:
                txn_date = _parse_date(date_words[0]['text'])
                if txn_date is None:
                    continue

                debit = credit = balance = None
                desc_parts = []

                for w in row_words:
                    x, text = w['x0'], w['text']
                    if x < _TXN_DATE_MAX_X:
                        continue  # transaction date cell
                    if _TXN_DATE_MAX_X <= x < _NARRATION_MIN_X:
                        continue  # value date column — skip
                    if _AMT_RE.match(text):
                        val = _to_decimal(text)
                        if x < mid_deb_cr:
                            debit = val
                        elif x < mid_cr_bal:
                            credit = val
                        else:
                            balance = val
                    elif _NARRATION_MIN_X <= x < deb_x:  # narration column
                        desc_parts.append(text)

                anchor_records[y] = {
                    'date': txn_date,
                    'debit': debit,
                    'credit': credit,
                    'balance': balance,
                    'desc': ' '.join(desc_parts),
                }
                last_anchor_y = y
                continue

            # ── Description continuation row ──────────────────────────────────
            if last_anchor_y is None:
                continue

            # Skip rows with amounts in the financial columns
            if any(_AMT_RE.match(w['text']) and w['x0'] >= deb_x for w in row_words):
                continue
            # Skip rows with words in the TXN DATE column (structural headers)
            if any(w['x0'] < _TXN_DATE_MAX_X for w in row_words):
                continue

            desc_words = [w for w in row_words if _NARRATION_MIN_X <= w['x0'] < deb_x]
            if desc_words:
                extra = ' '.join(w['text'] for w in desc_words)
                anchor_records[last_anchor_y]['desc'] += ' ' + extra

        # ── Build Transaction objects ─────────────────────────────────────────
        txns = []
        for rec in anchor_records.values():
            deb, cr = rec['debit'], rec['credit']
            if deb and deb > 0:
                tx_type, amount = 'debit', deb
            elif cr and cr > 0:
                tx_type, amount = 'credit', cr
            else:
                continue  # opening balance or zero-amount row

            txns.append(Transaction(
                date=rec['date'],
                bank='Equitas',
                description=rec['desc'].strip(),
                amount=amount,
                type=tx_type,
                balance=rec['balance'],
                category='',
                source='pdf_statement',
            ))

        return txns

    def _detect_col_bounds(self, header_words: list):
        deb_x = cr_x = bal_x = None
        for w in header_words:
            t = w['text'].lower()
            if t == 'debit':
                deb_x = w['x0']
            elif t == 'credit':
                cr_x = w['x0']
            elif t == 'balance':
                bal_x = w['x0']
        if deb_x and cr_x and bal_x:
            return deb_x, cr_x, bal_x
        return None
