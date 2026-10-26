"""Parse bank, card and Venmo statements into ONE normalized transactions table.

Formats are detected by CONTENT, not file name, so statements can be organized
in any folder layout under the data directory, or uploaded:

  * Ally Bank combined statement PDF        (checking + savings)
  * Elan-issued card statement PDF          (e.g. Fidelity Rewards Visa)
  * Fidelity / Elan card CSV export         ("Date","Transaction","Name","Memo","Amount")
  * Venmo monthly statement CSV
  * Apple Card CSV export

Sign convention for ``amount``: negative = money OUT of the account holder's
pocket, positive = money IN. Every parser returns the columns in ``COLUMNS``.

PDF parsing needs ``pymupdf``; without it PDFs are skipped and reported, and the
CSV sources still load.

Each PDF parser also returns a reconciliation check against the totals the
statement itself prints, so a parsing slip shows up as a visible mismatch rather
than silently wrong spending.

Everything parses from BYTES in memory (``load_files``); ``load_folder`` only
reads each file's bytes and hands them to the same function, so a folder and an
upload of the same statements give identical results. Nothing is written to disk.
"""
from __future__ import annotations

import csv
import io
import os
import re
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

COLUMNS = ["date", "source", "account", "description", "amount", "mcc",
           "counterparty", "note", "raw_type", "raw_category", "ref", "file"]

_MONEY_LINE = re.compile(r"^-?\$[\d,]+\.\d{2}$")
_FULL_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_SHORT_DATE = re.compile(r"^\d{2}/\d{2}$")
_ELAN_REF = re.compile(r"^(\d{4}|[A-Z]{3})$")
_ELAN_AMOUNT = re.compile(r"^\$([\d,]+\.\d{2})(CR)?$")
_CARD_PAYMENT = r"(?i)PAYMENT:?\s*THANK YOU|PAYMENT MADE BY ACCOUNT|\bAUTOPAY\b"


def _money(s: str) -> float:
    """'-$1,234.56' / '+ $1,234.56' / '$9.00CR' -> signed float (CR ignored)."""
    s = str(s).strip()
    neg = s.startswith("-")
    v = float(re.sub(r"[^\d.]", "", s) or 0.0)
    return -v if neg else v


def _row(**kw) -> dict:
    r = {c: "" for c in COLUMNS}
    r.update(kw)
    return r


# ---------------------------------------------------------------------------
# Ally Bank combined statement (PDF)
# ---------------------------------------------------------------------------

def _clean_ally_desc(parts: List[str]) -> str:
    """'<payee> | <transaction type>', e.g. 'CITY WATER BILL | ACH Withdrawal'.

    Payee first: merchant grouping keys on the start of the description, and
    with the type first every 'ACH Withdrawal' (mortgage, utilities, property
    tax) collapsed into a single merchant.
    """
    def clean(text: str) -> str:
        text = re.sub(r"~\s*Future", "", text)
        text = re.sub(r"Amount:\s*[\d.,]+\s*~\s*Tran:\s*\w+", "", text)
        return re.sub(r"\s+", " ", text).strip()
    parts = [p for p in parts if p]
    kind, payee = clean(parts[0]), ""
    # Ally repeats a fragment of the payee on the next line ('CITY WATER BILL'
    # then 'WATER BILL'); keep only lines that add something.
    for part in parts[1:]:
        c = clean(part)
        if c and c.upper() not in payee.upper():
            payee = f"{payee} {c}".strip()
    payee = clean(payee)     # 'Amount: … ~' and 'Tran: …' can sit on separate lines
    return f"{payee} | {kind}" if payee else kind


def parse_ally_lines(lines: List[str], file: str = "") -> Tuple[List[dict], List[dict]]:
    """Transactions + per-account balance checks from Ally statement text lines.

    Activity rows look like::

        08/31/2026 / ACH Withdrawal / <payee> / ... / $0.00 / -$80.00 / $1,920.00
        (date)       (description lines)            (credit) (debit)  (balance)
    """
    rows: List[dict] = []
    begin: Dict[str, float] = {}
    end: Dict[str, float] = {}
    acct = ""
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if line.startswith("Account Number:"):
            acct = line.split()[-1][-4:]
        if _FULL_DATE.match(line):
            j, desc = i + 1, []
            while j < n and not _MONEY_LINE.match(lines[j]) and not _FULL_DATE.match(lines[j]):
                if lines[j]:
                    desc.append(lines[j])
                j += 1
            money = []
            while j < n and _MONEY_LINE.match(lines[j]) and len(money) < 3:
                money.append(_money(lines[j]))
                j += 1
            head = desc[0] if desc else ""
            if head == "Beginning Balance" and money:
                begin.setdefault(acct, money[0])
            elif head == "Ending Balance" and money:
                end[acct] = money[0]
            elif len(money) == 3 and desc and not head.startswith("Page"):
                credit, debit, _balance = money
                rows.append(_row(
                    date=datetime.strptime(line, "%m/%d/%Y"), source="Ally",
                    account=f"Ally {acct}", description=_clean_ally_desc(desc),
                    amount=round(credit + debit, 2), file=file))
                i = j
                continue
        i += 1
    checks = []
    for a in sorted(set(begin) | set(end)):
        parsed = round(sum(r["amount"] for r in rows if r["account"] == f"Ally {a}"), 2)
        expected = round(end.get(a, 0.0) - begin.get(a, 0.0), 2)
        checks.append({"file": file, "source": "Ally", "what": f"Ally {a} balance change",
                       "expected": expected, "parsed": parsed})
    return rows, checks


# ---------------------------------------------------------------------------
# Elan-issued card statement (PDF) — e.g. Fidelity Rewards Visa
# ---------------------------------------------------------------------------

def _summary_value(lines: List[str], label: str) -> Optional[float]:
    """First money value after an exact summary label ('Purchases', 'Payments')."""
    for i, line in enumerate(lines):
        if line == label:
            for nxt in lines[i + 1:i + 4]:
                m = re.match(r"^\$([\d,]+\.\d{2})$", nxt)
                if m:
                    return float(m.group(1).replace(",", ""))
            return None
    return None


WordRow = Tuple[float, List[Tuple[float, str]]]   # (y, [(x, word), ...])

# Itinerary / "MERCHANDISE RETURN" lines sit ~10pt below their transaction; a
# bigger gap means the next row belongs to something else (page furniture).
_CONTINUATION_GAP = 13.0


def _word_rows(words) -> List[WordRow]:
    """Group pymupdf words (x0, y0, x1, y1, text, ...) into visual rows.

    The 'CR' credit marker is printed a point or two lower than its amount, so
    words within 3pt vertically belong to the same row.
    """
    rows: List[WordRow] = []
    cur: List[Tuple[float, str]] = []
    cur_y: Optional[float] = None
    for w in sorted(words, key=lambda w: (w[1], w[0])):
        if cur_y is None or w[1] - cur_y > 3.0:
            if cur:
                rows.append((cur_y, sorted(cur)))
            cur, cur_y = [], w[1]
        cur.append((w[0], w[4]))
    if cur:
        rows.append((cur_y, sorted(cur)))
    return rows


def parse_elan_rows(rows: List[WordRow], lines: List[str],
                    file: str = "") -> Tuple[List[dict], List[dict]]:
    """Transactions + summary checks from an Elan card statement.

    ``rows`` are visual rows of positioned words (see ``_word_rows``) and
    ``lines`` the plain text (used for the closing date and summary totals).

    Parsed by POSITION, not text order: the PDF's text stream batches every 'CR'
    marker at its section header, so reading lines in order turned payments and
    refunds into purchases. On the page, each transaction is one row — post
    date, optional trans date, ref, description, amount, and 'CR' for credits —
    with itinerary / return lines on the rows just below it.
    """
    text = "\n".join(lines)
    m = re.search(r"Closing Date:\s*(\d{2}/\d{2}/\d{4})", text)
    if not m:
        return [], []
    close = datetime.strptime(m.group(1), "%m/%d/%Y").date()
    card = re.search(r"Account ending in:\s*(\d{4})", text)
    name = "Fidelity Visa" if "Fidelity" in text else "Elan card"
    account = f"{name} {card.group(1)}" if card else name

    def _dated(md: str) -> datetime:
        mo, dy = int(md[:2]), int(md[3:])
        yr = close.year - (1 if (mo, dy) > (close.month, close.day) else 0)
        return datetime(yr, mo, dy)

    def _amount(words: List[str]):
        """(value, is_credit, index) of the row's amount, or None."""
        for k in range(len(words) - 1, -1, -1):
            am = _ELAN_AMOUNT.match(words[k])
            if am:
                credit = bool(am.group(2)) or "CR" in words[k + 1:]
                return float(am.group(1).replace(",", "")), credit, k
        return None

    txns: List[dict] = []
    open_txn: Optional[dict] = None
    for y, toks in rows:
        words = [t for _, t in toks]
        if words and _SHORT_DATE.match(words[0]):
            open_txn = None
            # The POST date, not the transaction date: card CSV exports date by
            # posting, and the same purchase must carry the same date in both or
            # overlapping CSV + PDF statements double count (the two dates differ
            # by 0-3 days for most purchases).
            k, txn = 1, words[0]
            if k < len(words) and _SHORT_DATE.match(words[k]):
                k += 1
            if k >= len(words) or not _ELAN_REF.match(words[k]):
                continue
            k += 1
            amt = _amount(words)
            end = amt[2] if amt and amt[2] >= k else len(words)
            desc = " ".join(words[k:end])
            if not desc:
                continue
            open_txn = {"date": txn, "desc": [desc], "y": y,
                        "x": toks[k][0] if k < len(toks) else 0.0,
                        "value": amt[0] if amt else None,
                        "credit": amt[1] if amt else False}
            txns.append(open_txn)
            continue
        # A continuation row: indented to the description column, right below.
        if (open_txn is not None and toks and toks[0][0] >= open_txn["x"] - 2
                and y - open_txn["y"] <= _CONTINUATION_GAP):
            amt = _amount(words)
            if amt and open_txn["value"] is not None:
                open_txn = None          # e.g. a "TOTAL THIS PERIOD" line
                continue
            if amt:
                open_txn["value"], open_txn["credit"] = amt[0], amt[1]
                words = words[:amt[2]]
            extra = " ".join(words)
            if extra:
                open_txn["desc"].append(extra)
            open_txn["y"] = y
        else:
            open_txn = None

    rows_out: List[dict] = []
    for t in txns:
        if t["value"] is None:
            continue
        rows_out.append(_row(
            date=_dated(t["date"]), source=name, account=account,
            description=re.sub(r"\s+", " ", " | ".join(t["desc"])).strip(),
            amount=t["value"] if t["credit"] else -t["value"], file=file))
    rows = rows_out

    checks = []
    is_payment = [bool(re.search(r"PAYMENT:?\s*THANK YOU", r["description"])) for r in rows]
    parsed_purchases = round(-sum(r["amount"] for r in rows if r["amount"] < 0), 2)
    parsed_payments = round(sum(r["amount"] for r, p in zip(rows, is_payment) if p), 2)
    parsed_credits = round(sum(r["amount"] for r, p in zip(rows, is_payment)
                               if r["amount"] > 0 and not p), 2)
    for label, parsed in (("Purchases", parsed_purchases), ("Payments", parsed_payments),
                          ("Other Credits", parsed_credits)):
        expected = _summary_value(lines, label)
        if expected is not None:
            checks.append({"file": file, "source": name, "what": f"{account} {label.lower()}",
                           "expected": expected, "parsed": parsed})
    return rows, checks


def _read_pdf(data: bytes) -> Tuple[List[str], List[WordRow]]:
    """Plain text lines plus positioned word rows (rows never span pages).

    Opened from the bytes in memory: no path, no temp file.
    """
    import pymupdf  # optional dependency; caller handles ImportError
    lines: List[str] = []
    rows: List[WordRow] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for page_no, page in enumerate(doc):
            lines += [ln.strip() for ln in page.get_text().splitlines()]
            # Offset y per page so a row on page 2 can never be read as a
            # continuation of the last transaction on page 1.
            rows += [(y + page_no * 10_000.0, toks)
                     for y, toks in _word_rows(page.get_text("words"))]
    return lines, rows


# ---------------------------------------------------------------------------
# CSV formats
# ---------------------------------------------------------------------------

# CSV exports append a foreign purchase's local amount to the merchant name
# ('RIDEAPP example CN - 50.0000 CHINA YUAN RENMINBI'); PDFs print it on its own
# line. Split it off the same way so both formats share one merchant line.
_FX_SUFFIX = re.compile(r"^(.*?)\s+-\s+([\d.,]+\s+[A-Z][A-Z ]+)$")


def parse_fidelity_csv(text: str, file: str = "") -> List[dict]:
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        memo = (r.get("Memo") or "").split(";")
        name = re.sub(r"\s+", " ", r["Name"]).strip()
        fx = _FX_SUFFIX.match(name)
        rows.append(_row(
            date=datetime.strptime(r["Date"], "%Y-%m-%d"), source="Fidelity Visa",
            account="Fidelity Visa", description=f"{fx.group(1)} | {fx.group(2)}" if fx else name,
            amount=float(r["Amount"]), mcc=memo[1].strip() if len(memo) > 1 else "",
            raw_type=r.get("Transaction", ""), file=file))
    return rows


def parse_venmo_csv(text: str, file: str = "") -> List[dict]:
    first = text.splitlines()[0] if text else ""
    m = re.search(r"\(@([^)]+)\)", first)
    me = m.group(1).replace("-", " ").strip() if m else ""
    body = "\n".join(text.splitlines()[2:])
    records = list(csv.DictReader(io.StringIO(body)))
    # You are on one side of every payment, so the most frequent name across
    # From/To is you. The handle is only a fallback: '@Pat-Doe-3' is not
    # the display name 'Pat Doe', and a mismatch flipped every row.
    names = [(r.get(k) or "").strip() for r in records for k in ("From", "To")]
    names = [n for n in names if n]
    if names:
        # Ties (a one-payment month: you and the other person appear once each)
        # go to the name the handle starts with.
        handle = me.lower()
        me = max(set(names), key=lambda n: (names.count(n), handle.startswith(n.lower())))
    rows = []
    for r in records:
        if not (r.get("ID") or "").strip() or not (r.get("Datetime") or "").strip():
            continue
        if (r.get("Status") or "").strip().lower() in ("failed", "cancelled", "canceled"):
            continue
        frm, to = (r.get("From") or "").strip(), (r.get("To") or "").strip()
        other = frm if frm and frm != me else to
        typ, note = (r.get("Type") or "").strip(), (r.get("Note") or "").strip()
        rows.append(_row(
            date=datetime.fromisoformat(r["Datetime"].strip()), source="Venmo",
            # Person first (merchant grouping keys on the start), type last.
            account="Venmo",
            description=(" — ".join(x for x in (other, note) if x) or "Venmo") + f" | Venmo {typ}",
            amount=_money(r.get("Amount (total)", "0")), counterparty=other,
            note=note, raw_type=typ, ref=r["ID"].strip(), file=file))
    return rows


def parse_apple_card_csv(text: str, file: str = "") -> List[dict]:
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        rows.append(_row(
            date=datetime.strptime(r["Transaction Date"], "%m/%d/%Y"), source="Apple Card",
            account="Apple Card", description=re.sub(r"\s+", " ", r["Description"]).strip(),
            amount=-float(r["Amount (USD)"]), counterparty=r.get("Merchant", ""),
            raw_type=r.get("Type", ""), raw_category=r.get("Category", ""), file=file))
    return rows


# ---------------------------------------------------------------------------
# Loaders — uploads and folders share ONE path: detect → parse → dedupe
# ---------------------------------------------------------------------------

def _detect_csv(text: str) -> Optional[str]:
    head = text[:300]
    if head.startswith("Account Statement - (@"):
        return "venmo"
    if "Transaction Date,Clearing Date,Description,Merchant" in head:
        return "apple_card"
    if '"Date","Transaction","Name","Memo","Amount"' in head:
        return "fidelity"
    return None


_CSV_PARSERS = {"venmo": parse_venmo_csv, "apple_card": parse_apple_card_csv,
                "fidelity": parse_fidelity_csv}


def _csv_text(data: bytes) -> str:
    """Decode CSV bytes exactly as ``open(path, encoding="utf-8-sig",
    errors="replace")`` reads the file (BOM dropped, newlines normalized), so an
    upload parses identically to the same file in a folder."""
    return io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig", errors="replace").read()


def _parse_one(name: str, data: bytes) -> Tuple[List[dict], List[dict], Optional[str]]:
    """``(rows, checks, problem)`` for one statement file's bytes."""
    if name.lower().endswith(".csv"):
        text = _csv_text(data)
        parser = _CSV_PARSERS.get(_detect_csv(text))
        if parser is None:
            return [], [], f"{name}: unrecognized CSV format, skipped"
        return parser(text, name), [], None
    if not name.lower().endswith(".pdf"):
        return [], [], f"{name}: not a CSV or PDF statement, skipped"
    try:
        lines, word_rows = _read_pdf(data)
    except ImportError:
        return [], [], f"{name}: PDF support needs `pip install pymupdf`, skipped"
    if "Ally Bank" in "\n".join(lines[:200]):
        rows, checks = parse_ally_lines(lines, name)
    elif "Elan Financial Services" in "\n".join(lines):
        rows, checks = parse_elan_rows(word_rows, lines, name)
    else:
        return [], [], f"{name}: unrecognized PDF statement, skipped"
    return rows, checks, None


def load_files(files: Iterable[Tuple[str, bytes]]) -> Tuple[pd.DataFrame, List[dict], List[str]]:
    """Parse statements given as ``(name, bytes)`` pairs, entirely in memory.

    ``name`` picks CSV vs PDF by its extension and labels each row's ``file``,
    which dedupe uses to tell overlapping statements apart — so a repeated name
    gets a " (2)" suffix. Files are taken in name order, so the result doesn't
    depend on the order they were picked in.

    Returns ``(transactions, checks, problems)``: the de-duplicated table, the
    statement reconciliation checks, and human-readable notes about files that
    were skipped.
    """
    rows: List[dict] = []
    checks: List[dict] = []
    problems: List[str] = []
    used: set = set()
    for name, data in sorted(files, key=lambda f: f[0]):
        label, n = name, 1
        while label in used:
            n += 1
            root, ext = os.path.splitext(name)
            label = f"{root} ({n}){ext}"
        used.add(label)
        try:
            r, c, problem = _parse_one(label, data)
        except Exception as exc:  # one bad file must not hide the rest
            problems.append(f"{label}: couldn't be read ({type(exc).__name__}: {exc})")
            continue
        rows += r
        checks += c
        if problem:
            problems.append(problem)
    df = pd.DataFrame(rows, columns=COLUMNS)
    if df.empty:
        return df, checks, problems
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float).round(2)
    return dedupe(df), checks, problems


def statement_files(data_dir: str) -> List[str]:
    out = []
    for root, dirs, files in os.walk(data_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if not f.startswith(".") and f.lower().endswith((".csv", ".pdf")):
                out.append(os.path.join(root, f))
    return sorted(out)


def load_folder(data_dir: str) -> Tuple[pd.DataFrame, List[dict], List[str]]:
    """Parse every supported statement under ``data_dir``.

    Reads each file's bytes and hands them to ``load_files`` — the path uploads
    take — labelled by their path relative to ``data_dir``. Same return value.
    """
    files: List[Tuple[str, bytes]] = []
    unreadable: List[str] = []
    for path in statement_files(data_dir):
        rel = os.path.relpath(path, data_dir)
        try:
            with open(path, "rb") as fh:
                files.append((rel, fh.read()))
        except OSError as exc:
            unreadable.append(f"{rel}: couldn't be read ({type(exc).__name__}: {exc})")
    df, checks, problems = load_files(files)
    return df, checks, unreadable + problems


def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """Drop the same transaction appearing in two overlapping statement files.

    Identical charges WITHIN one file are real (two $9 coffees the same day), so
    occurrences are numbered per file and only matching occurrence numbers
    across files collapse: the result keeps the larger per-file count.
    """
    df = df.copy()
    has_ref = df["ref"].astype(str) != ""
    with_ref = df[has_ref].drop_duplicates(["source", "ref"])
    rest = df[~has_ref].copy()
    # Key on the MERCHANT line only: PDFs append continuation lines (itinerary,
    # 'FOLIO: …', 'MERCHANDISE RETURN') that CSVs don't have, and with a short
    # merchant name those leaked into the key — 'HOTEL EXAMPLE IL | FOLIO: 1'
    # and 'HOTEL EXAMPLE IL' didn't match and the stay was counted twice.
    merchant = rest["description"].str.split(" | ", regex=False).str[0]
    rest["_k"] = (merchant.str.upper().str.replace(r"[^A-Z0-9]", "", regex=True).str[:16])
    # Issuers word the same card payment differently per format ('PAYMENT THANK
    # YOU' on the PDF, 'PAYMENT MADE BY ACCOUNT ENDING IN:…' in the CSV).
    rest.loc[merchant.str.contains(_CARD_PAYMENT, regex=True), "_k"] = "CARDPAYMENT"
    key = ["source", "date", "amount", "_k"]
    rest["_occ"] = rest.groupby(key + ["file"]).cumcount()
    # When the same purchase is in a CSV and a PDF, keep the CSV copy: it
    # carries the merchant category code, which PDFs don't.
    rest["_no_mcc"] = rest["mcc"].astype(str).str.strip() == ""
    rest = (rest.sort_values("_no_mcc", kind="stable")
            .drop_duplicates(key + ["_occ"]).drop(columns=["_k", "_occ", "_no_mcc"]))
    return pd.concat([with_ref, rest]).sort_values("date").reset_index(drop=True)


def coverage(df: pd.DataFrame, min_rows: int = 20, busy_per_month: float = 15,
             gap_days: int = 10, slack_days: int = 5) -> Tuple[List[dict], List[pd.Period]]:
    """Which months every source fully covers, and where the holes are.

    Averages over a month with a missing statement silently understate spending
    (a month with no card statement looks like a frugal month), so only COMPLETE
    months should feed them. A month is complete when every significant source
    (>= ``min_rows`` transactions) spans it, has at least one transaction in it,
    and — for daily-use sources like cards — has no run of ``gap_days`` without
    activity overlapping it by more than ``slack_days``.

    A sparse source (Venmo) can genuinely have a month with no activity, so its
    empty month only counts as MISSING when another account shows money moving
    to or from it that month (the bank funding or receiving from it). Treating
    every quiet month as missing threw away complete months for no reason.

    A source with too few rows to judge is ignored for completeness, but money
    paid to it from other accounts is reported as ``paid_unitemized`` — spending
    that exists but isn't itemized here.

    Returns ``(sources, complete_months)`` where each source dict has
    ``source, rows, first, last, gaps [(after, before)], empty_months,
    paid_unitemized, paid_months``.
    """
    if df.empty:
        return [], []
    df = df.assign(description=df["description"] if "description" in df else "",
                   amount=df["amount"] if "amount" in df else 0.0)
    slack = pd.Timedelta(days=slack_days)
    all_months = pd.period_range(df["date"].min(), df["date"].max(), freq="M")
    letters = df["description"].astype(str).str.upper().str.replace(r"[^A-Z]", "", regex=True)
    incomplete = set()
    sources = []
    for src, g in df.groupby("source"):
        d = g["date"].dt.normalize()
        first, last = d.min(), d.max()
        per_month = d.dt.to_period("M").value_counts()
        key = re.sub(r"[^A-Z]", "", str(src).upper())
        mentions = df[(df["source"] != src) & letters.str.contains(key, regex=False)] if key else df.iloc[0:0]
        mention_months = set(mentions["date"].dt.to_period("M"))
        busy = per_month.median() >= busy_per_month
        empty = [p for p in pd.period_range(first, last, freq="M") if p not in per_month.index
                 and (busy or p in mention_months)]
        gaps = []
        if busy:
            u = d.drop_duplicates().sort_values().reset_index(drop=True)
            gaps = [(a, b) for a, b in zip(u[:-1], u[1:]) if (b - a).days > gap_days]
        paid = mentions[mentions["amount"] < 0] if len(g) < min_rows else mentions.iloc[0:0]
        sources.append({"source": src, "rows": len(g), "first": first, "last": last,
                        "gaps": gaps, "empty_months": empty,
                        "paid_unitemized": round(float(-paid["amount"].sum()), 2),
                        "paid_months": sorted(set(paid["date"].dt.to_period("M")))})
        if len(g) < min_rows:
            continue
        for p in all_months:
            start, end = p.start_time.normalize(), p.end_time.normalize()
            if first > start + slack or last < end - slack or p in empty:
                incomplete.add(p)
                continue
            if any((min(b, end) - max(a, start)).days > slack_days for a, b in gaps):
                incomplete.add(p)
    return sources, [p for p in all_months if p not in incomplete]
