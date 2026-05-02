import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass
class Transaction:
    date: date
    bank: str
    description: str
    amount: Decimal
    type: Literal["credit", "debit"]
    balance: Decimal | None
    category: str
    source: str  # "email_alert" | "pdf_statement"

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "bank": self.bank,
            "description": self.description,
            "amount": str(self.amount),
            "type": self.type,
            "balance": str(self.balance) if self.balance is not None else None,
            "category": self.category,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Transaction":
        return cls(
            date=date.fromisoformat(d["date"]),
            bank=d["bank"],
            description=d["description"],
            amount=Decimal(d["amount"]),
            type=d["type"],
            balance=Decimal(d["balance"]) if d["balance"] is not None else None,
            category=d["category"],
            source=d["source"],
        )


@dataclass
class CashflowSummary:
    month: int
    year: int
    total_income: Decimal
    total_expenses: Decimal
    net_cashflow: Decimal
    by_category: dict[str, Decimal] = field(default_factory=dict)
    by_bank: dict[str, dict[str, Decimal]] = field(default_factory=dict)


def save_transactions(transactions: list[Transaction], path) -> None:
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump([t.to_dict() for t in transactions], f, indent=2)


def load_transactions(path) -> list[Transaction]:
    with open(path) as f:
        return [Transaction.from_dict(d) for d in json.load(f)]
