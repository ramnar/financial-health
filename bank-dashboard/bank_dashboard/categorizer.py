import re

_RULES: list[tuple[re.Pattern, str, str | None]] = [
    # (pattern, category, only_for_type)  — type None means any
    (re.compile(r"salary|sal/|payroll|stipend", re.I), "salary", "credit"),
    (re.compile(r"rent|housing|pg charges|maintenance", re.I), "rent", None),
    (re.compile(r"swiggy|zomato|dunzo|blinkit|restaurant|cafe|hotel|food|dhaba|biryani", re.I), "food", None),
    (re.compile(r"bigbasket|grofers|dmart|reliance\s*fresh|zepto|jiomart|more\s*super", re.I), "groceries", None),
    (re.compile(r"bsnl|airtel|jio|vi\b|vodafone|tata\s*sky|electricity|bescom|tneb|msedcl|water\s*bill|gas\s*bill|lpg", re.I), "utilities", None),
    (re.compile(r"uber|ola\b|rapido|irctc|redbus|petrol|fuel|metro|parking|toll", re.I), "transport", None),
    (re.compile(r"zerodha|groww|sbi\s*mf|navi|mutual\s*fund|demat|coin\b|kuvera|paytm\s*money|investment|lic\s*sip|ppf|nps\b|epf", re.I), "investments", None),
    (re.compile(r"\blic\b|insurance|premium|mediclaim|hdfc\s*life|icici\s*pru|star\s*health|care\s*health", re.I), "insurance", None),
    (re.compile(r"pharmacy|hospital|apollo|medplus|netmeds|1mg|doctor|clinic|lab\s*test|diagnostic", re.I), "medical", None),
    (re.compile(r"amazon|flipkart|myntra|ajio|nykaa|meesho|snapdeal|shopping", re.I), "shopping", None),
    (re.compile(r"netflix|spotify|hotstar|bookmyshow|prime\s*video|youtube\s*premium|zee5|sonyliv|entertainment", re.I), "entertainment", None),
    (re.compile(r"neft|imps|upi|rtgs|transfer|trf\b|fund\s*transfer", re.I), "transfers", None),
]

_DEFAULT = "other"


def categorize(description: str, tx_type: str) -> str:
    for pattern, category, only_type in _RULES:
        if only_type and only_type != tx_type:
            continue
        if pattern.search(description):
            return category
    return _DEFAULT
