import email
import email.message
import imaplib
from datetime import date
from pathlib import Path

from bank_dashboard.config import BankConfig

_IMAP_HOST = "imap.gmail.com"
_IMAP_PORT = 993


def connect(gmail_address: str, app_password: str) -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(_IMAP_HOST, _IMAP_PORT)
    mail.login(gmail_address, app_password)
    return mail


def _imap_date(d: date) -> str:
    return d.strftime("%d-%b-%Y")


def search_emails(
    mail: imaplib.IMAP4_SSL,
    imap_query: str,
    folder: str = "INBOX",
) -> list[email.message.Message]:
    try:
        mail.select(folder, readonly=True)
    except Exception:
        return []
    _, msg_nums = mail.search(None, imap_query)
    if not msg_nums or not msg_nums[0]:
        return []
    messages = []
    for num in msg_nums[0].split():
        _, data = mail.fetch(num, "(RFC822)")
        if data and data[0]:
            messages.append(email.message_from_bytes(data[0][1]))
    return messages


def _search_multi(
    mail: imaplib.IMAP4_SSL,
    queries_and_folders: list[tuple[str, str]],
) -> list[email.message.Message]:
    """Search multiple (query, folder) pairs and deduplicate by Message-ID."""
    seen: set[str] = set()
    results: list[email.message.Message] = []
    for query, folder in queries_and_folders:
        for msg in search_emails(mail, query, folder):
            mid = msg.get("Message-ID") or msg.get("Message-Id") or ""
            key = mid.strip() or str(id(msg))
            if key not in seen:
                seen.add(key)
                results.append(msg)
    return results


def extract_text_body(msg: email.message.Message) -> str:
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or "utf-8"
            return _strip_html(payload.decode(charset, errors="replace"))
    return ""


def _strip_html(html: str) -> str:
    from html.parser import HTMLParser

    class _Stripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    s = _Stripper()
    s.feed(html)
    return " ".join(s.parts)


def extract_pdf_attachments(
    msg: email.message.Message, output_dir: Path
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    counter = 0
    for part in msg.walk():
        content_type = part.get_content_type()
        filename = part.get_filename() or ""
        if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
            if not filename:
                filename = f"attachment_{counter}.pdf"
            counter += 1
            path = output_dir / filename
            stem, suffix = path.stem, path.suffix
            dup = 1
            while path.exists():
                path = output_dir / f"{stem}_{dup}{suffix}"
                dup += 1
            path.write_bytes(part.get_payload(decode=True))
            saved.append(path)
    return saved


def build_imap_query(
    sender: str | None,
    subject_keyword: str | None,
    date_start: date,
    date_end: date,
) -> str:
    from datetime import timedelta
    parts = []
    if sender:
        parts.append(f'FROM "{sender}"')
    if subject_keyword:
        parts.append(f'SUBJECT "{subject_keyword}"')
    parts.append(f'SINCE "{_imap_date(date_start)}"')
    parts.append(f'BEFORE "{_imap_date(date_end + timedelta(days=1))}"')
    return " ".join(parts)


def _statement_window(date_start: date, date_end: date) -> tuple[date, date]:
    """Statements for month M are emailed during month M+1.
    Search only within that following month so later statements don't bleed in.
    e.g. March statement → search April 1 – April 30.
    """
    from datetime import timedelta
    import calendar as _cal
    win_start = date_end + timedelta(days=1)
    last_day = _cal.monthrange(win_start.year, win_start.month)[1]
    win_end = win_start.replace(day=last_day)
    return win_start, win_end


def fetch_bank_statement_pdfs(
    mail: imaplib.IMAP4_SSL,
    bank: BankConfig,
    date_start: date,
    date_end: date,
    output_dir: Path,
) -> list[Path]:
    """Generic fetcher: searches all configured sender × folder combinations."""
    win_start, win_end = _statement_window(date_start, date_end)

    combos: list[tuple[str, str]] = []
    for sender in (bank.senders or [None]):
        query = build_imap_query(sender, bank.subject, win_start, win_end)
        for folder in bank.folders:
            print(f"  [Gmail] {bank.name} query folder={folder!r}: {query}")
            combos.append((query, folder))

    messages = _search_multi(mail, combos)

    # Fallback: search by date only in the first non-INBOX folder (dedicated label)
    if not messages:
        label_folders = [f for f in bank.folders if f != "INBOX"]
        if label_folders:
            query_date = build_imap_query(None, None, win_start, win_end)
            print(f"  [Gmail] {bank.name} fallback by date in {label_folders[0]!r}: {query_date}")
            messages = search_emails(mail, query_date, label_folders[0])

    print(f"  [Gmail] Found {len(messages)} {bank.name} statement email(s)")
    pdfs = []
    for msg in messages:
        pdfs.extend(extract_pdf_attachments(msg, output_dir))
    return pdfs
