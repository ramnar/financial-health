# Bank Dashboard

A personal cashflow dashboard that parses ICICI and Equitas bank e-Statement PDFs and displays spending summaries, charts, and transaction history in a Streamlit web app.

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

### 3. Configure credentials (optional — only needed for Gmail fetch via `run.py`)

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

## Running the Dashboard

### Option 1 — Upload PDFs directly (recommended)

Launch the Streamlit app:

```bash
venv/bin/streamlit run dashboard.py --server.headless true --browser.gatherUsageStats false
```

Then open your browser at:

```
http://localhost:8501
```

**Steps in the dashboard:**

1. In the sidebar, select the **statement month and year**.
2. Upload your **ICICI e-Statement PDF(s)** under "ICICI Bank".
3. Upload your **Equitas e-Statement PDF(s)** under "Equitas Bank".
4. Enter the **PDF password** for each bank (leave blank if not encrypted).
5. Click **Process PDFs**.

The dashboard will parse the PDFs and display your cashflow summary, charts, and transaction table.

---

### Option 2 — Fetch e-Statements from Gmail (`run.py`)

This fetches e-Statement PDF attachments directly from your Gmail inbox (transaction alert emails are ignored — only e-statement PDFs are processed).

```bash
# Previous month (default)
venv/bin/python run.py

# Specific month
venv/bin/python run.py --month 3 --year 2025

# Parse only, skip launching Streamlit
venv/bin/python run.py --no-dashboard --month 3 --year 2025
```

This requires a valid `config.ini` with Gmail credentials. The parsed transactions are cached to `data/transactions_cache.json` and the dashboard launches automatically.

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
├── dashboard.py              # Streamlit web app
├── run.py                    # Gmail fetch + parse pipeline
├── requirements.txt
├── config.ini                # Your credentials (not committed)
├── config.ini.template       # Credentials template
├── bank_dashboard/
│   ├── config.py             # Config loading
│   ├── models.py             # Transaction data model
│   ├── categorizer.py        # Spending category rules
│   ├── consolidator.py       # Deduplication and cashflow summary
│   ├── fetchers/
│   │   ├── gmail_fetcher.py  # Gmail IMAP fetcher (e-statements only)
│   │   └── pdf_fetcher.py    # PDF decryption
│   └── parsers/
│       ├── icici_pdf_parser.py
│       └── equitas_pdf_parser.py
└── data/
    ├── statements/           # Downloaded PDF attachments
    ├── decrypted/            # Decrypted PDFs
    ├── uploads/              # PDFs uploaded via dashboard
    └── transactions_cache.json
```
