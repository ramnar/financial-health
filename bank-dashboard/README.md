# Bank Dashboard

A personal cashflow dashboard that fetches ICICI and Equitas bank e-Statement PDFs from Gmail and displays spending summaries, charts, and transaction history in a Streamlit web app.

---

## Requirements

- Python 3.12+
- A virtual environment with dependencies installed

---

## Setup

### 1. Create and activate the virtual environment

```bash
cd bank-dashboard
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure credentials

Copy the template and fill in your details:

```bash
cp config.ini.template config.ini
```

Edit `config.ini`:

```ini
[gmail]
gmail_address      = your@gmail.com
gmail_app_password = xxxx xxxx xxxx xxxx   # Gmail App Password (not your login password)

[passwords]
icici_pdf_password   = <first4ofname><DDMM-of-DOB>
equitas_pdf_password = <DDMM-of-DOB><FIRST3OFNAME>
```

> **Note:** Gmail App Passwords can be generated at https://myaccount.google.com/apppasswords

---

## Usage

### Step 1 — Fetch e-Statements and parse transactions

```bash
# Previous month (default)
venv/bin/python run.py

# Specific month
venv/bin/python run.py --month 3 --year 2026

# Fetch and parse only, skip launching Streamlit
venv/bin/python run.py --no-dashboard --month 3 --year 2026
```

This fetches e-Statement PDF attachments directly from Gmail, parses transactions, and caches them to `data/transactions_cache.json`. The dashboard launches automatically unless `--no-dashboard` is passed.

### Step 2 — View the dashboard

If you used `--no-dashboard`, launch the dashboard separately:

```bash
venv/bin/streamlit run dashboard.py --server.headless true --browser.gatherUsageStats false
```

---

## Accessing the Dashboard

| URL | Description |
|-----|-------------|
| `http://localhost:8501` | Local access on the same machine |
| `http://<your-local-ip>:8501` | Access from another device on the same Wi-Fi |

To find your local IP:
```bash
hostname -I | awk '{print $1}'
```

---

## Project Structure

```
bank-dashboard/
├── dashboard.py              # Streamlit web app (read-only, displays cached data)
├── run.py                    # Gmail fetch + parse + cache pipeline
├── requirements.txt
├── config.ini                # Your credentials (not committed)
├── config.ini.template       # Credentials template
├── bank_dashboard/
│   ├── config.py             # Config loading
│   ├── models.py             # Transaction data model
│   ├── categorizer.py        # Spending category rules
│   ├── consolidator.py       # Deduplication and cashflow summary
│   ├── fetchers/
│   │   ├── gmail_fetcher.py  # Gmail IMAP fetcher
│   │   └── pdf_fetcher.py    # PDF decryption
│   └── parsers/
│       ├── icici_pdf_parser.py
│       └── equitas_pdf_parser.py
└── data/
    ├── statements/           # Downloaded PDF attachments
    ├── decrypted/            # Decrypted PDFs
    └── transactions_cache.json
```
