from bank_dashboard.parsers.equitas_pdf_parser import EquitasPdfParser
from bank_dashboard.parsers.icici_pdf_parser import IciciPdfParser

PARSERS = {
    "icici": IciciPdfParser,
    "equitas": EquitasPdfParser,
}
