from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

from bank_dashboard.models import Transaction


class BaseParser(ABC):
    def __init__(self, date_start: date, date_end: date):
        self.date_start = date_start
        self.date_end = date_end

    @abstractmethod
    def parse(self, source: Path | str) -> list[Transaction]:
        """Parse source (file path or text string) into a list of Transactions."""

    def _in_range(self, d: date) -> bool:
        return self.date_start <= d <= self.date_end

    def _filter_by_date(self, txns: list[Transaction]) -> list[Transaction]:
        return [t for t in txns if self._in_range(t.date)]
