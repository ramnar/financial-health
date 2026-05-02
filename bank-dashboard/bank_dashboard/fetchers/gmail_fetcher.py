import email
import email.message
import imaplib
from datetime import date
from pathlib import Path

_IMAP_HOST = "imap.gmail.com"
_IMAP_PORT = 993


def connect(gmail_address: str, app_password: str) -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(_IMAP_HOST, _IMAP_PORT)
    mail.login(gmail_address, app_password)
    return mail


def _imap_date(d: date) -> str:
    """Format date as DD-Mon-YYYY for IMAP SINCE/BEFORE criteria."""
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
    """Return decoded text/plain body. Falls back to stripping HTML if needed."""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")

    # Fallback: strip HTML tags
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or "utf-8"
            html = payload.decode(charset, errors="replace")
            return _strip_html(html)

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
    """Save all PDF attachments from a message to output_dir."""
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
            # Avoid overwriting an existing file with the same name
            stem = path.stem
            suffix = path.suffix
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
    """Build an IMAP search query string."""
    from datetime import timedelta
    parts = []
    if sender:
        parts.append(f'FROM "{sender}"')
    if subject_keyword:
        parts.append(f'SUBJECT "{subject_keyword}"')
    # IMAP SINCE is inclusive; BEFORE is exclusive — use day after date_end
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
    win_start = date_end + timedelta(days=1)                          # April 1
    last_day = _cal.monthrange(win_start.year, win_start.month)[1]
    win_end = win_start.replace(day=last_day)                        # April 30
    return win_start, win_end


def fetch_icici_alert_bodies(
    mail: imaplib.IMAP4_SSL, date_start: date, date_end: date
) -> list[str]:
    query = build_imap_query("customercare@icicibank.com", "Transaction alert", date_start, date_end)
    print(f"  [Gmail] ICICI alerts query: {query}")
    messages = search_emails(mail, query)
    print(f"  [Gmail] Found {len(messages)} ICICI alert emails")
    return [extract_text_body(m) for m in messages]


_ICICI_SENDERS = ["estatement@icicibank.com", "estatement@icici.bank.in"]
_ICICI_FOLDERS = ["INBOX", "1money/bank_icici"]


def fetch_icici_statement_pdfs(
    mail: imaplib.IMAP4_SSL, date_start: date, date_end: date, output_dir: Path
) -> list[Path]:
    win_start, win_end = _statement_window(date_start, date_end)
    combos = []
    for sender in _ICICI_SENDERS:
        query = build_imap_query(sender, "ICICI Bank Statement", win_start, win_end)
        for folder in _ICICI_FOLDERS:
            print(f"  [Gmail] ICICI query folder={folder!r}: {query}")
            combos.append((query, folder))
    messages = _search_multi(mail, combos)
    print(f"  [Gmail] Found {len(messages)} ICICI statement emails (deduplicated)")
    pdfs = []
    for msg in messages:
        pdfs.extend(extract_pdf_attachments(msg, output_dir))
    return pdfs


_EQUITAS_FOLDERS = ["INBOX", "1money/bank_equitas"]


def fetch_equitas_statement_pdfs(
    mail: imaplib.IMAP4_SSL, date_start: date, date_end: date, output_dir: Path
) -> list[Path]:
    win_start, win_end = _statement_window(date_start, date_end)
    query = build_imap_query("equitas", None, win_start, win_end)
    combos = [(query, folder) for folder in _EQUITAS_FOLDERS]
    for folder in _EQUITAS_FOLDERS:
        print(f"  [Gmail] Equitas query folder={folder!r}: {query}")
    messages = _search_multi(mail, combos)
    if not messages:
        print("  [Gmail] Retrying Equitas with subject keyword across folders...")
        query_subj = build_imap_query(None, "Statement", win_start, win_end)
        fallback_combos = [(query_subj, folder) for folder in _EQUITAS_FOLDERS]
        candidates = _search_multi(mail, fallback_combos)
        messages = [m for m in candidates if "equitas" in (m.get("From") or "").lower()]
    print(f"  [Gmail] Found {len(messages)} Equitas statement emails (deduplicated)")
    pdfs = []
    for msg in messages:
        pdfs.extend(extract_pdf_attachments(msg, output_dir))
    return pdfs
