import difflib
from decimal import Decimal

from bank_dashboard.models import CashflowSummary, Transaction


def consolidate(all_transactions: list[Transaction]) -> list[Transaction]:
    """Merge, deduplicate (ICICI email vs PDF), and sort by date."""
    deduped = _deduplicate(all_transactions)
    return sorted(deduped, key=lambda t: t.date)


def _deduplicate(txns: list[Transaction]) -> list[Transaction]:
    """
    For ICICI: email_alert and pdf_statement may both contain the same transaction.
    When a duplicate is found, keep the pdf_statement version (richer narration).
    A duplicate = same bank + same date + same amount + same type + description similarity > 0.8
    """
    pdf_txns = [t for t in txns if t.source == "pdf_statement"]
    email_txns = [t for t in txns if t.source == "email_alert"]
    other_txns = [t for t in txns if t.source not in ("pdf_statement", "email_alert")]

    kept = list(pdf_txns) + list(other_txns)

    for email_txn in email_txns:
        if not _has_pdf_duplicate(email_txn, pdf_txns):
            kept.append(email_txn)

    return kept


def _has_pdf_duplicate(email_txn: Transaction, pdf_txns: list[Transaction]) -> bool:
    for pdf_txn in pdf_txns:
        if (
            pdf_txn.bank == email_txn.bank
            and pdf_txn.date == email_txn.date
            and pdf_txn.amount == email_txn.amount
            and pdf_txn.type == email_txn.type
        ):
            ratio = difflib.SequenceMatcher(
                None,
                email_txn.description.lower(),
                pdf_txn.description.lower(),
            ).ratio()
            if ratio >= 0.5:  # Lower threshold since email narrations are shorter
                return True
    return False


def compute_cashflow(txns: list[Transaction], month: int, year: int) -> CashflowSummary:
    total_income = Decimal("0")
    total_expenses = Decimal("0")
    by_category: dict[str, Decimal] = {}
    by_bank: dict[str, dict[str, Decimal]] = {}

    for t in txns:
        if t.type == "credit":
            total_income += t.amount
        else:
            total_expenses += t.amount
            by_category[t.category] = by_category.get(t.category, Decimal("0")) + t.amount

        if t.bank not in by_bank:
            by_bank[t.bank] = {"income": Decimal("0"), "expenses": Decimal("0")}
        if t.type == "credit":
            by_bank[t.bank]["income"] += t.amount
        else:
            by_bank[t.bank]["expenses"] += t.amount

    return CashflowSummary(
        month=month,
        year=year,
        total_income=total_income,
        total_expenses=total_expenses,
        net_cashflow=total_income - total_expenses,
        by_category=by_category,
        by_bank=by_bank,
    )
