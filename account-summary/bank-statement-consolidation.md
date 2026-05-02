# Bank Statement Consolidation — Brainstorm & Plan

**Goal:** Fetch last month's account statements from all bank accounts and consolidate them into a single list to calculate cashflow (income and expenses).

---

## Questions to Answer First

- Which bank accounts need to be included? **ICICI Bank, Equitas Small Finance Bank**
- Are statements available via? **Email parsing (transaction alerts + e-statements from Gmail)**
- What is the desired output format? **Dashboard**
- What date range counts as "last month"? **1st to last day of a calendar month; month is configurable (defaults to previous month)**

---

## Approaches

### Option A — Manual Download + Parse
- Download statements as CSV/PDF from each bank's net banking portal
- Parse and normalize into a common schema
- Pros: Works for any bank, no API setup needed
- Cons: Manual effort each month, PDF parsing can be fragile

### Option B — Account Aggregator / Open Banking API
- Use a service like Finbox, Setu, or Perfios (India) to fetch statements programmatically
- Pros: Automated, consistent data format
- Cons: Requires onboarding/consent flow per bank, may have cost

### Option C — Email Parsing
- Many banks send monthly e-statements or transaction alerts via email
- Parse Gmail/inbox for statement attachments or transaction summaries
- Pros: Already available if emails are set up
- Cons: Inconsistent formats across banks

---

## Common Data Schema (Normalized Transaction)

| Field | Description |
|---|---|
| `date` | Transaction date |
| `bank` | Bank name / account identifier |
| `description` | Narration / merchant name |
| `amount` | Transaction amount |
| `type` | `credit` (income) or `debit` (expense) |
| `balance` | Running balance after transaction |
| `category` | Auto-tagged category (salary, food, rent, etc.) |

---

## Implementation Steps

- [ ] List all bank accounts to include
- [ ] Decide on data source approach (manual / API / email)
- [ ] Define the normalized schema
- [ ] Write parser/importer for each bank's format
- [ ] Merge all transactions into a single consolidated list
- [ ] Sort by date, de-duplicate if needed
- [ ] Compute cashflow summary: total income, total expenses, net
- [ ] Export to target format (CSV / JSON / spreadsheet)

---

## Cashflow Calculation

```
Total Income  = sum of all `credit` transactions
Total Expenses = sum of all `debit` transactions
Net Cashflow  = Total Income - Total Expenses
```

---

## Notes

