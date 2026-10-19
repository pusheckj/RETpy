"""Classify normalized transactions into spending vs. everything else.

Every row gets a ``kind``:

  spend     money that left for goods/services — counted
  payback   money people sent back for shared costs — SUBTRACTED from spending
  income    payroll, rent received, tax refunds, interest, work reimbursements
  transfer  money moving between your own accounts (card payments, savings
            moves, Venmo cash-outs) — counting these would double count
  excluded  real purchases deliberately left out (reimbursed work travel,
            items bought for others), with the reason recorded

``spend`` (positive = cost) is set for spend and payback rows only, so
``df.loc[df.kind.isin(["spend", "payback"]), "spend"].sum()`` is net spending.

Generic rules live in ``DEFAULT_RULES``. Anything specific to one person —
work-travel locations, the employer's reimbursement deposits, who pays rent —
belongs in a personal rules JSON stored next to the statements or uploaded with
them (never in this package); ``load_rules`` / ``parse_rules`` merge it on top
of the defaults.
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

import pandas as pd

CATEGORIES = [
    "Housing", "Utilities", "Groceries", "Dining", "Travel", "Auto & transport",
    "Shopping", "Jewelry & watches", "Subscriptions", "Health & fitness", "Pets", "Insurance",
    "Entertainment", "Personal care", "Home & garden", "Gifts & giving",
    "Fees & interest", "Cash & ATM", "People & shared", "Other",
]

DEFAULT_RULES: Dict = {
    # Your own money moving between accounts. Each purchase is counted once,
    # where it happened (on the card / in Venmo), so the PAYMENTS that settle a
    # card or fund Venmo must not be counted again.
    "transfer_patterns": [
        r"CARDMEMBER SERV", r"\bELAN\b.*PYMT", r"APPLECARD GSBANK", r"PAYMENT:?\s*THANK YOU",
        r"PAYMENT MADE BY ACCOUNT", r"PAYMENT RECEIVED",
        # AUTOPAY / EPAYMENT only next to a card issuer: 'VERIZON AUTOPAY' or
        # 'SDGE EPAYMENT' is a bill, not a transfer.
        r"(AMEX|AMERICAN EXPRESS|CHASE|CITI|DISCOVER|CAPITAL ONE|BARCLAY|SYNCHRONY).*(AUTOPAY|E-?PAYMENT)",
        r"CREDIT CRD", r"INTERNET TRANSFER (TO|FROM)",
        r"ALLY TO ALLY TRANSFER", r"REQUESTED TRANSFER", r"\bVENMO\b", r"APPLE CASH",
        r"BANK XFER", r"ACH TRNSFR", r"FUNDS TRANSFER",
        r"\bPROCEEDS\b",            # loan proceeds (e.g. a refinance payout) — borrowed money
    ],
    "venmo_transfer_types": ["Standard Transfer", "Instant Transfer", "Add Funds", "Bank Transfer"],
    "income_patterns": {
        "Payroll": [r"PAYROLL"],
        "Tax refund": [r"TAX ?REF", r"TAX ?RFD", r"TREAS\b"],
        "Interest": [r"^INTEREST PAID", r"INTEREST PAID"],
        "Deposit": [r"CHECK DEPOSIT", r"MOBILE DEPOSIT"],
    },
    # Credits from these on a BANK account are refunds of a housing cost
    # (escrow surplus), so they reduce Housing instead of counting as income.
    "housing_refund_patterns": [r"MORTGAGE", r"ESCROW"],   # + your lender in the rules JSON
    # --- personal rules (empty by default; set in the rules JSON) ---
    "merchant_categories": {},          # regex -> category, checked first
    "work_travel_locations": [],        # regex; matching card/bank purchases are reimbursed
    "work_travel_exceptions": [],       # regex; online merchants HQ'd in those cities
    "excluded_purchase_patterns": [],   # regex; e.g. hardware bought for other people
    "excluded_payback_note_patterns": [],  # regex on Venmo notes paying those back
    "reimbursement_patterns": [],       # regex; employer expense-reimbursement deposits
    # Venmo name -> income label ("Rent"), or {"label": "Rent", "min_amount": 400}
    # when that person ALSO sends small paybacks for shared costs.
    "income_counterparties": {},
    "transfer_reasons": {},             # regex -> label for a transfer (e.g. "Loan repayment")
    "transfer_counterparties": [],      # Venmo names that are you / your own accounts
    # Charges with no usable location (rideshares, airport shops) that are part
    # of a reimbursed trip: excluded only when within ``work_trip_window_days``
    # of a work-travel charge, so the same Uber on an ordinary day still counts.
    "work_trip_day_patterns": [],
    "work_trip_window_days": 1,
    # Spending that never appears in these statements (e.g. a partner's own
    # accounts), added as one line per month: [{"label", "amount", "category"}].
    "fixed_monthly": [],
}

# Merchant category codes (present in card CSV exports) -> category.
_MCC_RANGES = [
    ((742, 742), "Pets"), ((1520, 1799), "Home & garden"),
    ((3000, 3299), "Travel"), ((3351, 3441), "Travel"), ((3501, 3999), "Travel"),
    ((4111, 4131), "Auto & transport"), ((4511, 4582), "Travel"),
    ((4722, 4723), "Travel"), ((4784, 4789), "Auto & transport"),
    ((4812, 4816), "Utilities"), ((4899, 4899), "Subscriptions"), ((4900, 4900), "Utilities"),
    ((5200, 5261), "Home & garden"), ((5300, 5399), "Shopping"),
    ((5411, 5411), "Groceries"), ((5422, 5451), "Groceries"), ((5462, 5462), "Dining"),
    ((5499, 5499), "Groceries"), ((5511, 5599), "Auto & transport"),
    ((5600, 5799), "Shopping"), ((5811, 5814), "Dining"), ((5815, 5818), "Subscriptions"),
    ((5912, 5912), "Health & fitness"), ((5921, 5921), "Groceries"),
    ((5944, 5944), "Jewelry & watches"), ((5940, 5949), "Shopping"), ((5960, 5960), "Insurance"), ((5975, 5976), "Health & fitness"),
    ((5995, 5995), "Pets"), ((5900, 5999), "Shopping"),
    ((6010, 6011), "Cash & ATM"), ((6300, 6399), "Insurance"),
    ((7011, 7012), "Travel"), ((7210, 7217), "Personal care"), ((7230, 7230), "Personal care"),
    ((7297, 7298), "Personal care"), ((7512, 7519), "Travel"), ((7523, 7523), "Auto & transport"),
    ((7531, 7549), "Auto & transport"), ((7832, 7841), "Entertainment"),
    ((7911, 7999), "Entertainment"), ((7997, 7997), "Health & fitness"),
    ((8011, 8099), "Health & fitness"), ((8398, 8398), "Gifts & giving"),
    ((8661, 8661), "Gifts & giving"),
]

_APPLE_CARD_CATEGORIES = {
    "Restaurants": "Dining", "Grocery": "Groceries", "Gas": "Auto & transport",
    "Transportation": "Auto & transport", "Travel": "Travel", "Airlines": "Travel",
    "Hotels": "Travel", "Shopping": "Shopping", "Entertainment": "Entertainment",
    "Medical": "Health & fitness", "Utilities": "Utilities", "Alcohol": "Groceries",
}

# Keyword fallback when no MCC/category is available (PDF statements, Ally).
# Order matters: the first matching category wins.
_KEYWORDS = [
    ("Housing", r"MORTGA|COUNTY OF|TAX COLLECTOR|PROPERTY TAX|\bHOA (DUES|FEE)|HOMEOWNERS ASSOC"),
    ("Utilities", r"GAS & ELEC|SDG&?E|EDISON|PG&E|WATER BILL|\bWATER\b|SEWER|WASTE|"
                  r"\bCOX\b|SPECTRUM|AT&T|VERIZON|T-MOBILE|COMCAST|XFINITY|GOOGLE \*?FI"),
    ("Insurance", r"INSURANCE|GEICO|PROGRESSIVE|STATE FARM|ALLSTATE|LEMONADE"),
    ("Subscriptions", r"NETFLIX|SPOTIFY|HULU|DISNEY|YOUTUBE|APPLE\.COM/BILL|PATREON|"
                      r"OPENAI|CHATGPT|ANTHROPIC|CLAUDE\.AI|ADOBE|DROPBOX|AUDIBLE|\bHBO\b|PEACOCK|"
                      r"PARAMOUNT|NYTIMES"),
    ("Travel", r"\bAIR\b|AIRLINE|DELTA AIR|SOUTHWES|UNITED \d|ALASKA AIR|AMERICAN AIR|"
               r"JETBLUE|ALASKA AI|\bFOLIO\b|USCUSTOMS|TRUSTEDTRAVE|AMTRAK|HOTEL|\bINN\b|MARRIOTT|HILTON|HYATT|ALOFT|COURTYARD|AIRBNB|VRBO|"
               r"EXPEDIA|BOOKING\.COM|\bAVIS\b|HERTZ|ENTERPRISE RENT"),
    ("Pets", r"VETERINAR|\bVET\b|PETCO(?! PARK)|PETSMART|CHEWY|\bROVER\b"),
    ("Health & fitness", r"\bCVS\b|WALGREENS|PHARMACY|RITE AID|DENTAL|MEDICAL|CLINIC|"
                         r"\bGYM\b|FITNESS|YOGA|CLIMB"),
    ("Auto & transport", r"SUPERCHARGER|\bTESLA\b|\bARCO\b|\bSHELL\b|CHEVRON|EXXON|MOBIL\b|"
                         r"\bUBER\b(?! EATS)|\bLYFT\b|PARKI|\bMTA\b|NYCT|TRANSIT|COACH USA|\bMETRO\b|\bDMV\b|FASTRAK|TOLL|CAR WASH"),
    ("Groceries", r"MARKET|GROCER|TRADER JOE|WHOLE FOODS|\bVONS\b|RALPHS|SPROUTS|SAFEWAY|"
                  r"ALBERTSONS|COSTCO|SAMS ?CLUB|WHOLEFDS|GRISTEDES|FINE WIN|SMART & FINAL|99-CENTS|99 RANCH|H MART|INSTACART|LIQUOR"),
    ("Dining", r"CAFE|CAFFE|COFFEE|STARBUCKS|\bESPR\b|RESTAURANT|^TST\s?\*|PIZZA|TACO|RAMEN|"
               r"SUSHI|GRILL|BREW|\bBEER\b|KITCHEN|\bDELI\b|BAGEL|CHIPOTLE|CHICK-FIL-A|"
               r"MCDONALD|IN-N-OUT|DOORDASH|UBER EATS|GRUBHUB|FOOD\.APPLE\.COM|BAKERY|DONUT|"
               r"BOBA|\bBBQ\b|HUMMUS|\bPOKE\b|\bCAVA\b|BISTRO|NOODLE|DUMPLING|SANDWICH|SALAD|"
               r"SHAKE SHACK|\bPUB\b|TAVERN|\bWNGS\b|EATERY|DOMINO|POPEYES|HALAL|CHICKEN|JUICE|DONU|\bTHAI\b|\bPHO\b|BURGER|WINGS|HOTPOT|TAQUERIA|CANTINA"),
    ("Entertainment", r"TICKETMASTER|STUBHUB|\bAXS\b|PARTIFUL|EVENTBRITE|SEATGEEK|CINEMA|"
                      r"THEAT(ER|RE)|\bAMC\b|CONCERT|MUSEUM|\bAMNH\b|SMITHSONIAN|YACHT CLUB|\bZOO\b|STEAM|PLAYSTATION|NINTENDO"),
    ("Personal care", r"BARBER|SALON|\bSPA\b|\bHAIR\b|\bNAIL|SEPHORA|ULTA"),
    ("Home & garden", r"HOME DEPOT|LOWE'?S|ACE HARDWARE|IKEA|WAYFAIR|NURSERY"),
    ("Jewelry & watches", r"CHRONO24|JEWEL|WATCH(ES|CO|\.CO)|\bWATCH\b|ROLEX|OMEGA|TUDOR|CARTIER|TIFFANY"),
    ("Shopping", r"AMAZON|AMZN|TARGET|WALMART|EBAY|BEST BUY|NORDSTROM|MACY|UNIQLO|\bREI\b|"
                 r"\bNIKE\b|ETSY|BOOKS|BOOKSELLER"),
    ("Fees & interest", r"\bFEE\b|INTEREST CHARGE|FINANCE CHARGE"),
    ("People & shared", r"SPLITWISE|ZELLE"),
]
_KEYWORDS = [(c, re.compile(p, re.I)) for c, p in _KEYWORDS]

# Venmo notes are free text and often just emoji.
_NOTE_KEYWORDS = [
    ("Travel", r"trip|flight|air ?bnb|hotel|vegas|rosarito|cabo|camp|🏨|✈|🏙|🏝|🏖|🗺"),
    ("Utilities", r"water|electric|internet|wi-?fi|💡|🚿"),
    ("Dining", r"dinner|lunch|brunch|food|ramen|hotpot|pizza|papas|tacos?|bud|beer|drinks?|"
               r"🍕|🌯|🍔|🍣|🍜|🌭|🥗|🥔|☕|🍹|🍺|🍻|🍷"),
    ("Entertainment", r"ticket|party|concert|show|🎫|🎟|🎉|🎥|🎤"),
    ("Auto & transport", r"\bgas\b|uber|lyft|parking|⛽|🚗"),
    ("Groceries", r"groceries|costco|🛒"),
    ("Gifts & giving", r"gift|🎁"),
    ("Housing", r"🏠"),
]
_NOTE_KEYWORDS = [(c, re.compile(p, re.I)) for c, p in _NOTE_KEYWORDS]

REASON_WORK_TRAVEL = "Work travel (reimbursed)"
REASON_BOUGHT_FOR_OTHERS = "Bought for others"
REASON_PAID_BACK_FOR_OTHERS = "Paid back for items bought for others"
REASON_TRIP_EXTRA = "Work travel (ride/airport on a trip day)"
PAYBACK_FALLBACK = "People & shared"
# Kinds of purchases people actually split, used when a payback's note says
# nothing: a near-exact split of a dinner is evidence, a 1/3 "split" of your
# car insurance is a coincidence.
_SHAREABLE = {"Dining", "Travel", "Entertainment", "Groceries", "Utilities",
              "People & shared", "Auto & transport", "Gifts & giving"}
WORK_TRAVEL_REASONS = (REASON_WORK_TRAVEL, REASON_TRIP_EXTRA)


def merge_rules(personal: Optional[Dict]) -> Dict:
    """DEFAULT_RULES with personal rules (a parsed rules JSON) merged on top.

    Lists extend the defaults, dicts update them; unknown keys are ignored so a
    typo can't break the dashboard.
    """
    rules = json.loads(json.dumps(DEFAULT_RULES))
    for key, value in (personal or {}).items():
        if key not in rules:
            continue
        if isinstance(rules[key], list) and isinstance(value, list):
            rules[key] = rules[key] + value
        elif isinstance(rules[key], dict) and isinstance(value, dict):
            rules[key].update(value)
        elif not isinstance(rules[key], (list, dict)) and isinstance(value, type(rules[key])):
            rules[key] = value
    return rules


def load_rules(path: Optional[str]) -> Dict:
    """DEFAULT_RULES with the personal rules JSON at ``path`` merged on top."""
    if not path or not os.path.exists(path):
        return merge_rules(None)
    with open(path, encoding="utf-8") as fh:
        return merge_rules(json.load(fh))


_PATTERN_LISTS = ("transfer_patterns", "housing_refund_patterns", "work_travel_locations",
                  "work_travel_exceptions", "excluded_purchase_patterns",
                  "excluded_payback_note_patterns", "reimbursement_patterns",
                  "work_trip_day_patterns")


def parse_rules(data: bytes) -> Dict:
    """Rules from an uploaded rules JSON's bytes (same format as the file), in memory.

    Raises ValueError for anything unusable — not JSON, not an object, or a
    pattern that isn't a valid regex — so the caller can fall back to the
    defaults instead of failing later inside ``classify``.
    """
    personal = json.loads(data.decode("utf-8-sig"))
    if not isinstance(personal, dict):
        raise ValueError("the rules file must be a JSON object")
    rules = merge_rules(personal)
    patterns = [p for k in _PATTERN_LISTS for p in rules[k]]
    patterns += list(rules["merchant_categories"]) + list(rules["transfer_reasons"])
    patterns += [p for v in rules["income_patterns"].values()
                 for p in (v if isinstance(v, list) else [v])]
    for p in patterns:
        try:
            re.compile(p)
        except (re.error, TypeError) as exc:
            raise ValueError(f"invalid pattern {p!r} ({exc})") from None
    return rules


def _any(patterns: List[str], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def _mcc_category(mcc) -> Optional[str]:
    try:
        code = int(str(mcc).strip())
    except (TypeError, ValueError):
        return None
    for (lo, hi), cat in _MCC_RANGES:
        if lo <= code <= hi:
            return cat
    return None


def merchant_key(desc: str) -> str:
    """Letters-only prefix, so 'CHIPOTLE 0001 ANYTOWN' and 'CHIPOTLE 1234 ...'
    (or the same merchant on a CSV vs a PDF statement) share one key."""
    desc = re.sub(r"\*\s*\S*\d\S*", "", str(desc))       # order / booking IDs after '*'
    return re.sub(r"[^A-Z]", "", desc.upper())[:12]


def learned_categories(df: pd.DataFrame) -> Dict[str, str]:
    """Merchant key -> category, learned from rows that carry an MCC code.

    Card CSV exports include MCC codes but PDF statements don't, so without
    this the same coffee shop is 'Dining' in 2025 (CSV) and 'Other' in 2026
    (PDF). The most common MCC category per merchant wins.
    """
    if df.empty or "mcc" not in df:
        return {}
    cats = df["mcc"].map(_mcc_category)
    known = df.assign(_key=df["description"].map(merchant_key), _cat=cats)[cats.notna()]
    if known.empty:
        return {}
    return (known.groupby("_key")["_cat"]
            .agg(lambda s: s.value_counts().index[0]).to_dict())


def merchant_category(row, rules: Dict, learned: Optional[Dict[str, str]] = None) -> str:
    """Category for a card/bank purchase: personal override → MCC → same
    merchant's MCC seen elsewhere → issuer category → keyword → Other."""
    desc = row["description"]
    for pattern, cat in rules["merchant_categories"].items():
        if re.search(pattern, desc, re.I):
            return cat
    return (_mcc_category(row.get("mcc"))
            or (learned or {}).get(merchant_key(desc))
            or _APPLE_CARD_CATEGORIES.get(str(row.get("raw_category") or ""))
            or next((c for c, rx in _KEYWORDS if rx.search(desc)), None)
            or "Other")


def note_category(note: str) -> Optional[str]:
    return next((c for c, rx in _NOTE_KEYWORDS if rx.search(note or "")), None)


def _classify_row(row, rules: Dict, learned: Optional[Dict[str, str]] = None):
    """-> (kind, category, reason). ``kind`` is None for rows to drop."""
    desc, amt, src = row["description"], row["amount"], row["source"]
    if amt == 0:
        return None, None, ""

    if src == "Venmo":
        if row["raw_type"] in rules["venmo_transfer_types"] \
                or row["counterparty"] in rules["transfer_counterparties"]:
            return "transfer", None, "Venmo ↔ bank"
        if amt > 0:
            label = rules["income_counterparties"].get(row["counterparty"])
            if isinstance(label, dict):
                label = label.get("label") if amt >= float(label.get("min_amount", 0)) else None
            if label:
                return "income", None, label
            if _any(rules["excluded_payback_note_patterns"], row["note"]):
                return "excluded", None, REASON_PAID_BACK_FOR_OTHERS
            return "payback", note_category(row["note"]) or PAYBACK_FALLBACK, "Payback"
        return "spend", note_category(row["note"]) or "People & shared", ""

    if _any(rules["excluded_purchase_patterns"], desc):
        return "excluded", None, REASON_BOUGHT_FOR_OTHERS
    if _any(rules["transfer_patterns"], desc) or (src == "Apple Card" and row["raw_type"] == "Payment"):
        label = next((v for k, v in rules["transfer_reasons"].items() if re.search(k, desc, re.I)),
                     "Between your accounts")
        return "transfer", None, label
    if amt > 0:
        if _any(rules["reimbursement_patterns"], desc):
            return "income", None, "Work reimbursement"
        for label, pats in rules["income_patterns"].items():
            if _any(pats, desc):
                return "income", None, label
    if _any(rules["work_travel_locations"], desc) and not _any(rules["work_travel_exceptions"], desc):
        return "excluded", None, REASON_WORK_TRAVEL
    if amt > 0 and src == "Ally":
        if _any(rules["housing_refund_patterns"], desc):
            return "spend", "Housing", "Refund"
        return "income", None, "Other deposit"
    # Card credits that aren't payments are refunds: negative spend in the
    # merchant's own category, so a return cancels its purchase.
    return "spend", merchant_category(row, rules, learned), "Refund" if amt > 0 else ""


def classify(df: pd.DataFrame, rules: Dict) -> pd.DataFrame:
    """Add ``kind``, ``category``, ``reason`` and ``spend`` columns."""
    out = df.copy()
    if out.empty:
        for c in ("kind", "category", "reason"):
            out[c] = pd.Series(dtype=str)
        out["spend"] = pd.Series(dtype=float)
        out["eff_date"] = pd.Series(dtype="datetime64[ns]")
        return out
    learned = learned_categories(out)
    res = [_classify_row(r, rules, learned) for r in out.to_dict("records")]
    out["kind"] = [k for k, _, _ in res]
    out["category"] = [c or "" for _, c, _ in res]
    out["reason"] = [r for _, _, r in res]
    out = out[out["kind"].notna()].copy()
    _match_paybacks_to_excluded(out)
    _exclude_trip_day_extras(out, rules)
    out["eff_date"] = out["date"]
    _assign_paybacks(out)
    counted = out["kind"].isin(["spend", "payback"])
    out["spend"] = 0.0
    out.loc[counted, "spend"] = -out.loc[counted, "amount"]
    return out.reset_index(drop=True)


def _split_error(r: float, max_k: int = 6):
    """How far a payback/cost ratio is from an even split 1/k -> (error, k)."""
    errs = [(abs(r - 1.0 / k) * k, k) for k in range(1, max_k + 1)]
    return min(errs)


def _assign_refunds(df: pd.DataFrame, window_days: int = 90) -> None:
    """Count a merchant refund in the month of the purchase it reverses (in place).

    A return posted the next month otherwise inflates the purchase month and
    deflates the refund month — and if that month is incomplete, the refund
    vanishes from every average while the purchase stays.
    """
    refunds = df[(df["kind"] == "spend") & (df["amount"] > 0)]
    buys = df[(df["kind"] == "spend") & (df["amount"] < 0)]
    for idx, r in refunds.iterrows():
        key = merchant_key(r["description"])
        cand = buys[(buys["date"] <= r["date"]) & (buys["date"] >= r["date"] - pd.Timedelta(days=window_days))
                    & (-buys["amount"] >= r["amount"] - 0.01)]
        cand = cand[cand["description"].map(merchant_key) == key]
        if len(cand):
            df.at[idx, "eff_date"] = cand["date"].max()


def _assign_paybacks(df: pd.DataFrame, window_days: int = 30) -> None:
    """Put each payback in the category -- and month -- of the cost it repays (in place).

    1. The note's category stands when it says something ('Water bill', 'Air bnb').
    2. Same-amount paybacks within 3 days are one split (four friends' $75
       'Beach trip' / '🏠') and share the group's majority category.
    3. If a purchase in the prior ``window_days`` matches -- same category and
       within 2% of an even split (nearest such purchase wins) -- the payback counts in THAT purchase's month, so
       a trip's cost and its paybacks land together (and a gap month drops both).
    4. A note that says nothing ('💥', 'Thank you') takes a purchase's category
       only on a near-exact split of a shareable purchase.
    Each purchase absorbs paybacks up to its own cost.
    """
    pb = df[df["kind"] == "payback"].sort_values("date")
    _assign_refunds(df)
    if pb.empty:
        return
    # 2. split groups
    groups: List[List[int]] = []
    for idx, row in pb.iterrows():
        g = next((g for g in groups if abs(df.at[g[0], "amount"] - row["amount"]) < 0.01
                  and (row["date"] - df.at[g[0], "date"]).days <= 3), None)
        (g.append(idx) if g is not None else groups.append([idx]))
    for g in groups:
        if len(g) < 2:
            continue
        cats = [df.at[i, "category"] for i in g if df.at[i, "category"] != PAYBACK_FALLBACK]
        if cats:
            winner = max(set(cats), key=lambda c: (cats.count(c), -cats.index(c)))
            # Only a REAL majority overrides: three $20 paybacks for 'dinner',
            # 'uber' and 'water bill' are three different costs.
            if cats.count(winner) >= 2:
                df.loc[g, "category"] = winner
    # 3./4. tie to the purchase it repays
    buys = df[(df["kind"] == "spend") & (df["amount"] < 0)]
    absorbed: Dict[int, float] = {}
    for idx in pb.index:
        p = df.loc[idx]
        # Trips are booked months ahead (a March Airbnb for a June weekend).
        days = 120 if p["category"] == "Travel" else window_days
        cand = buys[(buys["date"] >= p["date"] - pd.Timedelta(days=days))
                    & (buys["date"] <= p["date"] + pd.Timedelta(days=3))]
        best, best_key = None, None
        for b_idx, b in cand.iterrows():
            cost = -b["amount"]
            if cost < 20 or cost - absorbed.get(b_idx, 0.0) < p["amount"] * 0.98:
                continue
            err, k = _split_error(p["amount"] / cost)
            if p["category"] != PAYBACK_FALLBACK:
                ok = b["category"] == p["category"] and err < 0.02
            else:
                ok = b["category"] in _SHAREABLE and err < 0.01 and k <= 4
            # Nearest qualifying purchase first: with dozens of dinners in the
            # window, SOME will look like a 1/k split by chance, so the split
            # quality only breaks ties.
            key = (abs((p["date"] - b["date"]).days), err)
            if ok and (best_key is None or key < best_key):
                best, best_key = b_idx, key
        if best is None:
            continue
        df.at[idx, "eff_date"] = df.at[best, "date"]
        if p["category"] == PAYBACK_FALLBACK:
            df.at[idx, "category"] = df.at[best, "category"]
        absorbed[best] = absorbed.get(best, 0.0) + p["amount"]


def _exclude_trip_day_extras(df: pd.DataFrame, rules: Dict) -> None:
    """Exclude location-less trip costs (in place): a rideshare or airport
    purchase within N days of a reimbursed work-travel charge.

    Uber/Lyft descriptors carry no city and airport shops bill from the home
    airport, so location rules can't see that they belong to a trip.
    """
    patterns = rules.get("work_trip_day_patterns") or []
    if not patterns:
        return
    n = int(rules.get("work_trip_window_days", 1))
    days = df.loc[df["reason"] == REASON_WORK_TRAVEL, "date"].dt.normalize()
    window = {d + pd.Timedelta(days=k) for d in days for k in range(-n, n + 1)}
    hit = (df["kind"] == "spend") & (df["source"] != "Venmo") \
        & df["date"].dt.normalize().isin(window) \
        & df["description"].map(lambda t: _any(patterns, t))
    df.loc[hit, ["kind", "category", "reason"]] = ["excluded", "", REASON_TRIP_EXTRA]


def _match_paybacks_to_excluded(df: pd.DataFrame, tol: float = 0.02, days: int = 45,
                                min_amount: float = 100.0) -> None:
    """Re-label paybacks that settle an EXCLUDED purchase (in place).

    A payback note doesn't always say what it's for ("Thank you!!"), but when
    the amount matches an item bought for someone else, subtracting it from
    spending would cancel spending that was never counted -- understating real
    spending by the full payback. Each excluded purchase settles at most one
    payback.
    """
    bought = df[df["reason"] == REASON_BOUGHT_FOR_OTHERS]
    bought = bought[bought["amount"] < 0]
    if bought.empty:
        return
    used = set()
    for idx, row in df[(df["kind"] == "payback") & (df["amount"] >= min_amount)].iterrows():
        for b_idx, b in bought.iterrows():
            if b_idx in used:
                continue
            cost = -b["amount"]
            if abs(row["amount"] - cost) <= max(tol * cost, 5.0) \
                    and abs((row["date"] - b["date"]).days) <= days:
                df.loc[idx, ["kind", "category", "reason"]] = \
                    ["excluded", "", REASON_PAID_BACK_FOR_OTHERS]
                used.add(b_idx)
                break
