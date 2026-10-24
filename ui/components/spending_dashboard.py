"""Spending tab — category spending and trends from your own statements.

Statements come from one of two places, both parsed by the same code
(utils/spending_parsers.py: ``load_folder`` reads files' bytes and calls
``load_files``, which uploads use directly):

  * Local (your own machine): a folder OUTSIDE this package — the path is
    stored in ~/.config/retirement-sim/spending.json, or set SPENDING_DATA_DIR.
    With no folder set, the upload below is offered instead.
  * Hosted (utils/hosting.is_hosted()): uploads only. The server's filesystem
    is never read on a visitor's behalf — no folder setting, no settings file,
    no SPENDING_DATA_DIR. Uploaded files are parsed in memory and kept only in
    that visitor's st.session_state (never in a cache shared across sessions).

Every row is classified (see utils/spending_rules.py) and the tab shows:

  * average monthly spending over COMPLETE months only (a missing statement
    would otherwise look like a frugal month)
  * a monthly trend stacked by category, with paybacks subtracted
  * category totals, a per-category drill-down, top merchants
  * a searchable transaction list and an audit of everything left out

Nothing parsed here is written to disk.
"""
from __future__ import annotations

import functools
import json
import os
import re
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go

try:
    from utils.spending_parsers import load_files, load_folder, statement_files, coverage
    from utils.spending_rules import (load_rules, parse_rules, classify, merchant_key,
                                      REASON_WORK_TRAVEL, REASON_BOUGHT_FOR_OTHERS,
                                      REASON_PAID_BACK_FOR_OTHERS, WORK_TRAVEL_REASONS)
    from utils.hosting import is_hosted
    from utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark
    from utils.formatting import money, money_md
    from utils.derived import compute_expenses_today
    from utils.expense_categories import (CATEGORIES, HOUSING, HOUSING_KEYS, HOUSING_STATEMENT,
                                          INPUTS, MIRRORS)
except ImportError:  # pragma: no cover
    from ui.utils.spending_parsers import load_files, load_folder, statement_files, coverage  # type: ignore
    from ui.utils.spending_rules import (load_rules, parse_rules, classify, merchant_key,  # type: ignore
                                         REASON_WORK_TRAVEL, REASON_BOUGHT_FOR_OTHERS,
                                         REASON_PAID_BACK_FOR_OTHERS, WORK_TRAVEL_REASONS)
    from ui.utils.hosting import is_hosted  # type: ignore
    from ui.utils.plot_theme import style_fig, show_chart, PLOTLY_CONFIG, is_dark  # type: ignore
    from ui.utils.formatting import money, money_md  # type: ignore
    from ui.utils.derived import compute_expenses_today  # type: ignore
    from ui.utils.expense_categories import (CATEGORIES, HOUSING, HOUSING_KEYS,  # type: ignore
                                             HOUSING_STATEMENT, INPUTS, MIRRORS)

SETTINGS_PATH = os.path.expanduser("~/.config/retirement-sim/spending.json")
RULES_FILENAME = "spending_rules.json"
UPLOAD_STATE = "sp_uploads"      # st.session_state key: this visitor's uploads + parsed result
PRIVACY_NOTE = "Your files are processed in memory for this session only and never saved."
FORMATS_NOTE = ("Recognised: Ally Bank statements (PDF), Fidelity / Elan card statements "
                "(CSV export or PDF), Venmo monthly statements (CSV) and Apple Card exports "
                "(CSV). Anything else is skipped and listed under Data.")
# The Expenses section's own buckets, from the list both screens are built on
# (utils/expense_categories.py): (label, plan keys, statement categories).
EXPENSE_GROUPS = [(HOUSING, HOUSING_KEYS, HOUSING_STATEMENT)] + [
    (c.label, (c.key,), c.statement) for c in CATEGORIES]
ESTIMATE_SOURCE = "Estimate"     # rows added from fixed monthly estimates, not statements
GROUPS = [g for g, _, _ in EXPENSE_GROUPS]
_GROUP_OF = {c: g for g, _, cats in EXPENSE_GROUPS for c in cats}


def expense_group(category: str) -> str:
    """Expenses-section bucket for a detailed spending category."""
    return _GROUP_OF.get(category, "Other / miscellaneous")


def plan_monthly(overrides: Dict, group: str) -> float:
    """The plan's monthly input for an expense bucket (mortgage, else rent, for Housing)."""
    keys = next(k for g, k, _ in EXPENSE_GROUPS if g == group)
    vals = [float(overrides.get(k, 0) or 0) for k in keys]
    return next((v for v in vals if v > 0), 0.0)
PERIODS = ["Last 12 months", "Year to date", "All complete months"]

# One fixed color per expense bucket, in EXPENSE_GROUPS order: navy, rose,
# violet, sand, cyan, plum, steel. Muted tones by the owner's plotting standard
# (no red/green/yellow/orange), ordered so every NEIGHBOUR in the stack and
# around the donut stays distinct: adjacent-pair colour-blind dE >= 9.7 and
# normal-vision dE >= 15.8 in both modes (dataviz validate_palette.js). Light
# tones sit below 3:1 on the light surface, so charts also carry labels, hover
# values and a table.
_SERIES = {
    False: ["#2e4f7a", "#e09ab5", "#8a78c9", "#cbb08e", "#4b9cc4", "#8a5a8c", "#8fa3b8", "#7d6e63"],
    True: ["#6b8fd0", "#e09ab5", "#8574cf", "#cbb08e", "#5ab4d8", "#a35f9f", "#b8c0cc", "#806f63"],
}
# Estimated (not statement) amounts are drawn hatched, so they never read as data.
_ESTIMATE_PATTERN = "/"
_FOLD = {False: "#b5b4ac", True: "#5d5c57"}
_INK = {False: "#1f2937", True: "#e5e7eb"}
_SURFACE = {False: "#ffffff", True: "#0e1117"}
# The app's chart cards have 10px side padding with overflow hidden, but the
# chart is sized to the card's full width, so ~11px at the right edge is cut
# off. Keep content (edge labels, legends) clear of that strip.
_CARD_CLIP = 26


def _mon(p: pd.Period) -> str:
    return p.strftime("%b %Y")


def _day(ts: pd.Timestamp) -> str:
    # No "%-d": it is POSIX-only and raises on Windows.
    return f"{ts:%b} {ts.day}, {ts.year}"


# ---------------------------------------------------------------------------
# Settings & loading
# ---------------------------------------------------------------------------

def configured_data_dir() -> str:
    """The local statements folder: SPENDING_DATA_DIR, else the settings file.

    Always "" when hosted, without reading either: a visitor must never be able
    to make the app read the server's filesystem.
    """
    if is_hosted():
        return ""
    env = os.environ.get("SPENDING_DATA_DIR", "").strip()
    if env:
        return os.path.expanduser(env)
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as fh:
            return os.path.expanduser(json.load(fh).get("data_dir", ""))
    except (OSError, ValueError):
        return ""


def save_data_dir(path: str) -> None:
    if is_hosted():
        raise RuntimeError("Hosted mode never writes settings on the server.")
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
        json.dump({"data_dir": path}, fh, indent=2)


def _fingerprint(data_dir: str) -> Tuple:
    """Changes whenever a statement or the rules file is added/edited/removed."""
    paths = statement_files(data_dir) + [os.path.join(data_dir, RULES_FILENAME)]
    out = []
    for p in paths:
        try:
            st_ = os.stat(p)
            out.append((p, st_.st_mtime_ns, st_.st_size))
        except OSError:
            pass
    return tuple(out)


def prepare(raw: pd.DataFrame, checks: List[dict], problems: List[str], rules: Dict) -> Dict:
    """Everything the tab shows, from parsed statements + rules (folder or upload)."""
    tx = classify(raw, rules)
    if not tx.empty:
        # The month a row COUNTS in: a payback tied to a purchase counts in the
        # purchase's month, so a trip and its paybacks land together.
        tx["month"] = tx["eff_date"].dt.to_period("M")
        tx["merchant"] = tx["description"].str.split(" | ", regex=False).str[0].str.slice(0, 42)
    sources, complete = coverage(raw)           # statements only: estimates never fill a gap
    tx = add_fixed_items(tx, rules)
    return {"tx": tx, "checks": checks, "problems": problems,
            "sources": sources, "complete": complete}


# Folder mode only (local): process-wide, keyed by path + file stats. Uploads
# never come through here — this cache is shared by every session.
@functools.lru_cache(maxsize=4)
def _load_cached(data_dir: str, _fp: Tuple) -> Dict:
    raw, checks, problems = load_folder(data_dir)
    return prepare(raw, checks, problems, load_rules(os.path.join(data_dir, RULES_FILENAME)))


def add_fixed_items(tx: pd.DataFrame, rules: Dict) -> pd.DataFrame:
    """One row per month for each fixed estimate (rules "fixed_monthly"), across
    the months the statements cover. Marked with source ESTIMATE_SOURCE."""
    items = rules.get("fixed_monthly") or []
    if tx.empty or not items:
        return tx
    rows = []
    for m in pd.period_range(tx["month"].min(), tx["month"].max(), freq="M"):
        for it in items:
            amt = float(it.get("amount", 0) or 0)
            if amt <= 0:
                continue
            d = m.start_time
            rows.append({c: "" for c in tx.columns} | {
                "date": d, "eff_date": d, "month": m, "source": ESTIMATE_SOURCE,
                "account": ESTIMATE_SOURCE, "description": it.get("label", "Fixed estimate"),
                "merchant": it.get("label", "Fixed estimate"), "amount": -amt, "spend": amt,
                "kind": "spend", "category": it.get("category", "Partner spending"),
                "reason": "Fixed monthly estimate"})
    if not rows:
        return tx
    return pd.concat([tx, pd.DataFrame(rows, columns=tx.columns)], ignore_index=True)


def load(data_dir: str) -> Dict:
    """Folder mode (local only)."""
    if is_hosted():
        raise RuntimeError("Hosted mode never reads a server folder; use load_uploaded.")
    return _load_cached(data_dir, _fingerprint(data_dir))


def load_uploaded(files: Iterable[Tuple[str, bytes]], rules_json: Optional[bytes] = None) -> Dict:
    """Same result as ``load`` but from uploaded ``(name, bytes)`` pairs, parsed in memory.

    ``rules_json`` is an uploaded rules file's bytes (DEFAULT_RULES apply without
    one; an unusable one is reported in ``rules_error`` and the defaults used).
    Deliberately NOT cached: functools and st.cache_* caches are shared by every
    session in the server process. The caller keeps the result in the visitor's
    own st.session_state.
    """
    raw, checks, problems = load_files(files)
    rules, rules_error = load_rules(None), None
    if rules_json is not None:
        try:
            rules = parse_rules(rules_json)
        except ValueError as exc:
            rules_error = f"Your rules file was ignored ({exc}); using the default rules."
    return {**prepare(raw, checks, problems, rules), "rules_error": rules_error}


# ---- per-session uploads: st.session_state only, never disk or a shared cache

def _upload_store(st) -> Dict:
    """This session's uploads: ``{"files": {name: bytes}, "rules": (name, bytes) | None}``
    plus ``"data"``, the parsed result, dropped whenever the files change."""
    store = st.session_state.get(UPLOAD_STATE)
    if store is None:
        store = st.session_state[UPLOAD_STATE] = {"files": {}, "rules": None}
    return store


def _uploader_key(st) -> str:
    return f"sp_upload_{st.session_state.get('sp_upload_n', 0)}"


def _reset_uploader(st) -> None:
    # A fresh key gives an empty widget (Streamlit then frees the old one's files).
    st.session_state["sp_upload_n"] = st.session_state.get("sp_upload_n", 0) + 1


def _take_uploads(st) -> None:
    """Uploader on_change: move the picked files into the session store and empty
    the widget. The store is the one source of truth, and unlike widget state it
    survives switching to the plan view and back. A JSON file is the rules file;
    a file with an existing name replaces it."""
    store = _upload_store(st)
    for f in st.session_state.get(_uploader_key(st)) or []:
        if f.name.lower().endswith(".json"):
            store["rules"] = (f.name, f.getvalue())
        else:
            store["files"][f.name] = f.getvalue()
    store.pop("data", None)
    _reset_uploader(st)


def _clear_uploads(st) -> None:
    st.session_state.pop(UPLOAD_STATE, None)
    _reset_uploader(st)


def _uploaded_data(st) -> Dict:
    """Parsed uploads, computed once per change and kept in this session only."""
    store = _upload_store(st)
    if "data" not in store:
        store["data"] = load_uploaded(list(store["files"].items()),
                                      store["rules"][1] if store["rules"] else None)
    return store["data"]


# ---------------------------------------------------------------------------
# Pure summaries (tested without Streamlit)
# ---------------------------------------------------------------------------

def counted(tx: pd.DataFrame) -> pd.DataFrame:
    """Rows that make up net spending: purchases/refunds and paybacks."""
    return tx[tx["kind"].isin(["spend", "payback"])]


def period_bounds(months: List[pd.Period], complete: List[pd.Period],
                  choice: str) -> Tuple[pd.Period, pd.Period]:
    """[start, end] months for a period choice, ending at the last COMPLETE
    month so a half-finished statement month never anchors the window."""
    end = complete[-1] if complete else months[-1]
    if choice == "Year to date":
        start = pd.Period(year=end.year, month=1, freq="M")
    elif choice == "All complete months":
        start = complete[0] if complete else months[0]
    else:
        start = end - 11
    return start, end


ONE_OFF = 500.0      # a purchase this size or larger is a one-off, not routine


def apply_filters(tx: pd.DataFrame, groups: Optional[List[str]] = None,
                  drop_oneoffs: bool = False) -> pd.DataFrame:
    """Keep only the counted spending the user chose to look at.

    ``groups`` limits counted rows to those expense buckets; ``drop_oneoffs``
    removes counted rows of ONE_OFF dollars or more (purchases and the paybacks
    for them alike). Rows that aren't spending (transfers, income, excluded)
    pass through untouched, so the Data tab still sees them.
    """
    if tx.empty:
        return tx
    counted_mask = tx["kind"].isin(["spend", "payback"])
    keep = counted_mask
    if groups is not None:
        keep = keep & tx["category"].map(expense_group).isin(groups)
    if drop_oneoffs:
        keep = keep & ((tx["spend"].abs() < ONE_OFF) | (tx["source"] == ESTIMATE_SOURCE))
    return tx[~counted_mask | keep]


def moving_average(series: pd.Series, complete: List[pd.Period], window: int) -> pd.Series:
    """Trailing mean over the last ``window`` months, skipping incomplete ones.

    A month with a missing statement is a hole, not a $0 month, so it drops out
    of the average instead of dragging it down. Needs at least half the window.
    """
    good = set(complete)
    masked = series.where([m in good for m in series.index])
    return masked.rolling(window, min_periods=max(2, (window + 1) // 2)).mean()


def monthly_table(tx: pd.DataFrame, start: pd.Period, end: pd.Period,
                  groups: Optional[List[str]] = None) -> pd.DataFrame:
    """Months x [expense groups..., 'Net'] in the Expenses section's buckets.

    Each bucket is your real share: purchases net of refunds AND of what people
    paid you back for it. 'Net' is the month's total over the shown buckets.
    """
    months = pd.period_range(start, end, freq="M")
    shown = [g for g in GROUPS if groups is None or g in groups]
    s = counted(tx)
    s = s[(s["month"] >= start) & (s["month"] <= end)]
    s = s.assign(group=s["category"].map(expense_group))
    table = (s.groupby(["month", "group"])["spend"].sum().unstack(fill_value=0.0)
             .reindex(index=months, columns=shown, fill_value=0.0))
    table["Net"] = table.sum(axis=1)
    return table.fillna(0.0)


def actual_plan(tx: pd.DataFrame, complete: List[pd.Period], owns: bool = True,
                partner: bool = True) -> Dict[str, int]:
    """The plan's monthly inputs as your statements have them: {config key: $/month}.

    The one definition of "actual" behind both the Plan vs. actual table and
    "Use my actual spending", so after a click the two always agree. Each
    category is its average over ALL complete months, after paybacks, one-offs
    included. Housing is today's payment plus separately paid housing costs
    (``current_housing``): the mortgage input for an owner, rent for a renter.
    Partner spending only when the statements carry an estimate for it and
    there is a partner; otherwise there is nothing to copy and the plan's own
    figure stands. Whole dollars, within each input's range.
    """
    avg = group_averages(tx, complete)
    housing_key = HOUSING_KEYS[0] if owns else HOUSING_KEYS[1]
    out = {housing_key: current_housing(tx, complete)}
    for c in CATEGORIES:
        if c.partner_only and not (partner and avg[c.label] > 0):
            continue
        out[c.key] = avg[c.label]
    return {k: int(min(max(round(v), 0), INPUTS[k][1])) for k, v in out.items()}


def plan_vs_actual(overrides: Dict, actual: Dict[str, int],
                   groups: Optional[List[str]] = None) -> pd.DataFrame:
    """Plan input vs ``actual_plan`` per expense category, $/month. Actual is
    NaN for a category the statements don't have (partner, without an estimate)."""
    rows = []
    for g, keys, _ in EXPENSE_GROUPS:
        if groups is not None and g not in groups:
            continue
        a = next((actual[k] for k in keys if k in actual), None)
        rows.append({"Expense category": g, "Your plan": plan_monthly(overrides, g),
                     "Actual": float("nan") if a is None else float(a)})
    out = pd.DataFrame(rows, columns=["Expense category", "Your plan", "Actual"])
    out["Difference"] = out["Actual"] - out["Your plan"]
    return out


def differing(overrides: Dict, actual: Dict[str, int]) -> List[str]:
    """Categories whose plan input isn't what ``actual_plan`` would set."""
    g = plan_vs_actual(overrides, actual)
    return list(g.loc[g["Difference"].abs() >= 0.5, "Expense category"])


def category_table(tx: pd.DataFrame, start: pd.Period, end: pd.Period) -> pd.DataFrame:
    """Counted transactions per detailed category in the period: count, total,
    average and largest purchase, biggest total first."""
    s = counted(tx)
    s = s[(s["month"] >= start) & (s["month"] <= end)]
    if s.empty:
        return pd.DataFrame(columns=["Expense category", "Category", "Transactions",
                                     "Total", "Average", "Largest"])
    g = s.groupby("category").agg(Transactions=("spend", "size"), Total=("spend", "sum"),
                                  Average=("spend", "mean"), Largest=("spend", "max")).reset_index()
    g.insert(0, "Expense category", g["category"].map(expense_group))
    return (g.rename(columns={"category": "Category"})
            .sort_values("Total", ascending=False).reset_index(drop=True))


def category_summary(tx: pd.DataFrame, start: pd.Period, end: pd.Period,
                     complete: List[pd.Period], include_housing: bool = True) -> pd.DataFrame:
    """Per category: average per complete month, per year, share, count.

    COMPLETE months only. A period total over months with a missing card
    statement undercounts card categories but not bank ones (the mortgage still
    shows), which skews both totals and shares — so nothing here is summed over
    a gap. Paybacks are netted into the category their note points to (a
    friend's share of a trip reduces Travel): your real share of each.
    """
    s = counted(tx)
    if not include_housing:
        s = s[s["category"] != "Housing"]
    good = [m for m in complete if start <= m <= end]
    on_good = s[s["month"].isin(good)]
    per = on_good.groupby("category")["spend"].sum() / max(len(good), 1)
    out = pd.DataFrame({"Per month": per, "Per year": per * 12,
                        "Transactions": on_good.groupby("category").size()})
    out["Expense category"] = [expense_group(c) for c in out.index]
    pos = out["Per month"].clip(lower=0).sum()
    out["Share"] = out["Per month"].clip(lower=0) / pos if pos else 0.0
    return out.sort_values("Per month", ascending=False)


def kpis(tx: pd.DataFrame, start: pd.Period, end: pd.Period,
         complete: List[pd.Period], unitemized_sources: Tuple[str, ...] = ()) -> Dict[str, float]:
    """Headline numbers — all over COMPLETE months only, so a missing statement
    can't drag an average down or make reimbursements look larger than the
    travel they repaid. ``unitemized_sources`` are accounts whose transactions
    aren't loaded; money paid to them is reported as an upper bound of the
    spending that's missing."""
    s = counted(tx)
    good = [m for m in complete if start <= m <= end]
    on_good = s[s["month"].isin(good)]
    n = max(len(good), 1)
    in_range = tx[tx["month"].isin(good)]
    keys = [re.sub(r"[^A-Z]", "", x.upper()) for x in unitemized_sources]
    letters = in_range["description"].str.upper().str.replace(r"[^A-Z]", "", regex=True)
    to_unitemized = in_range[(in_range["kind"] == "transfer") & (in_range["amount"] < 0)
                             & letters.map(lambda t: any(k and k in t for k in keys))]
    return {
        "unitemized_per_month": -to_unitemized["amount"].sum() / n,
        "months": len(good),
        "per_month": on_good["spend"].sum() / n,
        "per_month_ex_housing": on_good.loc[on_good["category"] != "Housing", "spend"].sum() / n,
        "paybacks_per_month": -on_good.loc[on_good["kind"] == "payback", "spend"].sum() / n,
        "work_travel": -in_range.loc[in_range["reason"].isin(WORK_TRAVEL_REASONS), "amount"].sum(),
        "bought_for_others": -in_range.loc[in_range["reason"] == REASON_BOUGHT_FOR_OTHERS, "amount"].sum(),
        "reimbursed": in_range.loc[in_range["reason"] == "Work reimbursement", "amount"].sum(),
    }


def current_housing(tx: pd.DataFrame, complete: List[pd.Period], last_n: int = 3,
                    tol: float = 0.03) -> float:
    """Housing per month NOW: today's payment + other housing costs since it began.

    The payment is the month's largest housing outflow (mortgage or rent), taken
    as the median of the last ``last_n`` complete months. Property tax,
    insurance or HOA paid separately are added as their average over the months
    since the payment reached today's level — not over a longer window, or
    pre-refinance tax bills now inside an escrowed payment would count twice.
    """
    h = counted(tx)
    h = h[(h["category"] == "Housing") & h["month"].isin(complete)]
    if h.empty or not complete:
        return 0.0
    total = h.groupby("month")["spend"].sum().reindex(complete, fill_value=0.0)
    pay = h.groupby("month")["spend"].max().reindex(complete, fill_value=0.0)
    now = float(pay.iloc[-last_n:].median())
    since = len(pay)
    while since > 0 and abs(pay.iloc[since - 1] - now) <= tol * max(now, 1.0):
        since -= 1
    window = slice(since, len(pay)) if since < len(pay) else slice(-last_n, None)
    other = float((total - pay).iloc[window].mean())
    return now + other


def top_merchants(tx: pd.DataFrame, start: pd.Period, end: pd.Period,
                  category: Optional[str] = None, n: int = 15,
                  complete: Optional[List[pd.Period]] = None) -> pd.DataFrame:
    s = counted(tx)
    s = s[(s["month"] >= start) & (s["month"] <= end) & (s["kind"] == "spend")]
    if complete is not None:
        s = s[s["month"].isin(complete)]
    if category:
        s = s[(s["category"] == category) | (s["category"].map(expense_group) == category)]
    if s.empty:
        return pd.DataFrame(columns=["Merchant", "Category", "Total", "Visits"])
    s = s.assign(_k=s["description"].map(merchant_key))
    g = s.groupby("_k").agg(Merchant=("merchant", lambda m: m.value_counts().index[0]),
                            Category=("category", lambda c: c.value_counts().index[0]),
                            Total=("spend", "sum"), Visits=("spend", "size"))
    return g.sort_values("Total", ascending=False).head(n).reset_index(drop=True)


def group_averages(tx: pd.DataFrame, months: List[pd.Period]) -> pd.Series:
    """Average $/month per expense bucket over ``months`` (housing included)."""
    s = counted(tx)
    s = s[s["month"].isin(months)]
    avg = s.groupby(s["category"].map(expense_group))["spend"].sum() / max(len(months), 1)
    return avg.reindex(GROUPS, fill_value=0.0)


# ---------------------------------------------------------------------------
# "Use my actual spending": shared by this tab and the Expenses section
# ---------------------------------------------------------------------------

def statement_data(st) -> Optional[Dict]:
    """This session's statements without drawing the tab; None if there are none."""
    data_dir = configured_data_dir()                 # always "" when hosted
    try:
        if data_dir and os.path.isdir(data_dir):
            data = load(data_dir)
        elif (st.session_state.get(UPLOAD_STATE) or {}).get("files"):
            data = _uploaded_data(st)
        else:
            return None
    except Exception:  # unreadable files: the tab itself says why
        return None
    return data if data["complete"] and not data["tx"].empty else None


def session_actual(st, data: Dict) -> Dict[str, int]:
    """``actual_plan`` for this session's household (owner or renter, partner or not)."""
    ov = st.session_state.get("user_overrides", {}) or {}
    rent_own = st.session_state.get("se_rent_own")
    owns = rent_own == "Own home" if rent_own else float(ov.get("HOME_VALUE", 0) or 0) > 0
    partner = float(ov.get("PARTNER_AGE", 0) or 0) > 0
    return actual_plan(data["tx"], data["complete"], owns, partner)


def use_actual(st, actual: Dict[str, int]) -> None:
    """Button callback: copy ``actual`` into the plan and the inputs that show it.
    Runs before the next run draws any widget, so the inputs may be set here."""
    ov = st.session_state["user_overrides"]
    for key, value in actual.items():
        ov[key] = value
        if key in MIRRORS:
            ov[MIRRORS[key]] = value
        st.session_state[INPUTS[key][0]] = value


def _and(names: List[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def sync_control(st, data: Dict, key: str) -> None:
    """Whether the plan's monthly inputs match your statements, and the button
    that makes them match."""
    actual = session_actual(st, data)
    off = differing(st.session_state.get("user_overrides", {}) or {}, actual)
    complete = data["complete"]
    span = f"all {len(complete)} complete months, {_mon(complete[0])} – {_mon(complete[-1])}"
    if not off:
        st.caption(f"✓ Matches your statements ({span}).")
    else:
        names = _and(off) if len(off) <= 3 else f"{len(off)} categories"
        st.caption(f"{names} {'differs' if len(off) == 1 else 'differ'} from your statements ({span}).")
    st.button("Use my actual spending", key=key, on_click=use_actual, args=(st, actual),
              disabled=not off, icon=":material/sync:",
              help="Sets each monthly amount to its average over all complete months, and "
                   "housing to your current payment. Partner spending changes only if your "
                   "statements include an estimate for it.")


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _chart(st, build, key: str, config: dict) -> None:
    """Regular + phone version of a chart (see plot_theme.show_chart)."""
    show_chart(st, build, key, config)


def _label_color(hex_color: str) -> str:
    """White or near-black slice label, whichever contrasts more (WCAG luminance)."""
    c = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    return "#ffffff" if 1.05 / (lum + 0.05) >= (lum + 0.05) / 0.05 else "#111827"


def pie_figure(avg: pd.Series, dark: bool, compact: bool = False) -> go.Figure:
    """Donut of the average month, one slice per expense bucket (fixed colors).

    Legend on the right carries each bucket's $/month, so it fits half a row.
    The explicit domain + fixed height keep the ring inside its card.
    ``compact`` (phones): the legend goes under the ring, which gets the width.
    """
    vals = avg.clip(lower=0)
    vals = vals[vals > 0]
    labels = [f"{g}  {money(v)}" for g, v in vals.items()]
    fig = go.Figure(go.Pie(
        labels=labels, values=list(vals.values), sort=False, direction="clockwise", hole=0.7,
        domain=dict(x=[0.12, 0.88], y=[0.36, 1.0]) if compact else dict(x=[0.0, 0.42], y=[0.0, 1.0]),
        marker=dict(colors=[_SERIES[dark][GROUPS.index(g)] for g in vals.index],
                    line=dict(color=_SURFACE[dark], width=2),
                    pattern=dict(shape=[_ESTIMATE_PATTERN if g == "Partner spending" else ""
                                        for g in vals.index],
                                 fgcolor=_SURFACE[dark], fgopacity=0.45, fillmode="overlay")),
        textposition="inside", texttemplate="%{percent:.0%}", insidetextorientation="horizontal",
        insidetextfont=dict(color=["#111827" if dark else _label_color(_SERIES[dark][GROUPS.index(g)])
                                    for g in vals.index]),   # dark: every mid-tone slice takes the same dark label
        hovertemplate="<b>%{label}</b> per month (%{percent:.1%})<extra></extra>"))
    fig.update_layout(height=460 if compact else 340, showlegend=True,
                      uniformtext=dict(minsize=10, mode="hide"),
                      legend=(dict(orientation="h", x=0.5, xanchor="center", y=0.32, yanchor="top",
                                   font=dict(size=11.5)) if compact
                              else dict(x=0.45, y=0.5, yanchor="middle", font=dict(size=11.5))),
                      margin=dict(t=10, b=10, l=10, r=_CARD_CLIP),
                      # True total (a bucket netting negative can't be a slice but still counts).
                      annotations=[dict(text=f"<b>{money(avg.sum())}</b><br><span style='font-size:11px'>per month</span>",
                                        x=0.5 if compact else 0.21, y=0.68 if compact else 0.5,
                                        xref="paper", yref="paper", showarrow=False,
                                        font=dict(size=14, color=_INK[dark]))])
    return fig


def _month_x(months) -> List[pd.Timestamp]:
    return [p.start_time for p in months]


def _shade_incomplete(fig: go.Figure, months, incomplete: List[pd.Period], dark: bool) -> None:
    """Shade months with missing statements and LABEL each run of them.

    Shading alone read as "you spent nothing" (a month with no card statement
    still shows the bank's mortgage/utilities, so its bar looks tiny but real).
    """
    shown = [p for p in incomplete if months[0] <= p <= months[-1]]
    runs: List[List[pd.Period]] = []
    for p in shown:
        if runs and p == runs[-1][-1] + 1:
            runs[-1].append(p)
        else:
            runs.append([p])
    for run in runs:
        x0, x1 = run[0].start_time, (run[-1] + 1).start_time
        fig.add_vrect(x0=x0, x1=x1, layer="below", fillcolor=_FOLD[dark], opacity=0.18,
                      line_width=0)
        # Placed by hand: plotly's vrect annotation can't take a midpoint of dates.
        # Anchor to the inner edge when the band touches the chart edge, or the
        # label is clipped.
        x, anchor = x0 + (x1 - x0) / 2, "center"
        if run[-1] == months[-1]:
            x, anchor = x1, "right"
        elif run[0] == months[0]:
            x, anchor = x0, "left"
        fig.add_annotation(x=x, y=0.99, xref="x", yref="paper", yanchor="top", xanchor=anchor,
                           text="Missing statements" if len(run) > 1 else "Partial",
                           showarrow=False, font=dict(size=11, color=_INK[dark]))


def monthly_figure(table: pd.DataFrame, incomplete: List[pd.Period], dark: bool,
                   ma: Optional[pd.Series] = None, window: int = 0,
                   compact: bool = False) -> go.Figure:
    """Stacked monthly spending by bucket. ``compact`` (phones): a month label
    every third month, so the labels don't collide."""
    x = _month_x(table.index)
    fig = go.Figure()
    colors = _SERIES[dark]
    for g in [c for c in table.columns if c != "Net"]:
        if not table[g].any():
            continue
        fig.add_trace(go.Bar(
            x=x, y=table[g], name=g,
            # Fixed slot per bucket: hiding Housing never repaints the others.
            marker=dict(color=colors[GROUPS.index(g)], line=dict(color=_SURFACE[dark], width=2),
                        # overlay: hatch drawn OVER the fill (the default 'replace' drew
                        # the hatch on nothing and the estimate disappeared).
                        pattern=dict(shape=_ESTIMATE_PATTERN if g == "Partner spending" else "",
                                     fgcolor=_SURFACE[dark], fgopacity=0.45, fillmode="overlay")),
            xperiod="M1", xperiodalignment="middle",
            hovertemplate=f"<b>{g}</b><br>%{{x|%b %Y}}: %{{y:$,.0f}}<extra></extra>"))
    with_ma = ma is not None and window > 0
    fig.add_trace(go.Scatter(
        x=x, y=table["Net"], name="Total", mode="markers" if with_ma else "lines+markers",
        line=dict(color=_INK[dark], width=2), marker=dict(size=8, color=_INK[dark],
                                                           line=dict(color=_SURFACE[dark], width=2)),
        xperiod="M1", xperiodalignment="middle",
        hovertemplate="<b>Total</b><br>%{x|%b %Y}: %{y:$,.0f}<extra></extra>"))
    if with_ma:
        fig.add_trace(go.Scatter(
            x=x, y=ma.reindex(table.index).values, name=f"{window}-month average", mode="lines",
            connectgaps=True, line=dict(color=_INK[dark], width=2.5),
            xperiod="M1", xperiodalignment="middle",
            hovertemplate=f"<b>{window}-month average</b><br>%{{x|%b %Y}}: %{{y:$,.0f}}<extra></extra>"))
    _shade_incomplete(fig, list(table.index), incomplete, dark)
    fig.update_xaxes(range=[table.index[0].start_time, (table.index[-1] + 1).start_time])
    fig.update_layout(barmode="relative", barcornerradius=4, bargap=0.25, height=440,
                      hovermode="closest", legend=dict(orientation="h", y=-0.24 if compact else -0.15),
                      margin=dict(t=36, b=10, l=10, r=_CARD_CLIP),
                      yaxis=dict(tickformat="$,.0f", title=None),
                      xaxis=dict(title=None, dtick="M3" if compact else "M1", tickformat="%b<br>%Y",
                                 ticklabelmode="period"))
    return fig


def category_trend_figure(tx: pd.DataFrame, category: str, start: pd.Period, end: pd.Period,
                          incomplete: List[pd.Period], dark: bool, window: int = 3,
                          compact: bool = False) -> go.Figure:
    months = pd.period_range(start, end, freq="M")
    s = counted(tx)
    s = s[(s["category"] == category) | (s["category"].map(expense_group) == category)]
    first = min(start, s["month"].min()) if not s.empty else start
    hist = pd.period_range(first, end, freq="M")
    per_all = s.groupby("month")["spend"].sum().reindex(hist, fill_value=0.0)
    per = per_all.reindex(months, fill_value=0.0)
    # Average over the months BEFORE the window too, so a 12-month line is
    # meaningful from the first month shown; missing-statement months are skipped.
    rolling = (moving_average(per_all, [m for m in hist if m not in incomplete], window)
               .reindex(months) if window else None)
    x = _month_x(months)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x, y=per, name=category, xperiod="M1", xperiodalignment="middle",
        marker=dict(color=_SERIES[dark][0], line=dict(color=_SURFACE[dark], width=2)),
        hovertemplate=f"<b>{category}</b><br>%{{x|%b %Y}}: %{{y:$,.0f}}<extra></extra>"))
    if rolling is not None:
        fig.add_trace(go.Scatter(
            x=x, y=rolling.values, name=f"{window}-month average", mode="lines", connectgaps=True,
            line=dict(color=_INK[dark], width=2), xperiod="M1", xperiodalignment="middle",
            hovertemplate=f"<b>{window}-month average</b><br>%{{x|%b %Y}}: %{{y:$,.0f}}<extra></extra>"))
    _shade_incomplete(fig, list(months), incomplete, dark)
    fig.update_xaxes(range=[start.start_time, (end + 1).start_time])
    fig.update_layout(height=330, barcornerradius=4, bargap=0.3, hovermode="x unified",
                      legend=dict(orientation="h", y=-0.3), margin=dict(t=36, b=10, l=10, r=_CARD_CLIP),
                      yaxis=dict(tickformat="$,.0f", title=None),
                      xaxis=dict(title=None, dtick="M3" if compact else "M1", tickformat="%b<br>%Y",
                                 ticklabelmode="period"))
    return fig


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def _merchants_per_year(tx, start, end, complete, category, n) -> pd.DataFrame:
    good = [m for m in complete if start <= m <= end]
    t = top_merchants(tx, start, end, category, n=n, complete=complete)
    t["Per year"] = t["Total"] / max(len(good), 1) * 12
    return t[["Merchant", "Category", "Per year", "Visits"]]


def _settings_form(st, data_dir: str, ok: bool) -> None:
    """Local-only folder setting. Never shown when hosted: a path box would let a
    visitor point the app at any server directory."""
    if is_hosted():
        return
    path = st.text_input(
        "Statements folder", value=data_dir, key="sp_dir_input",
        help="Folder with your bank / card / Venmo statements (CSV or PDF, any "
             "sub-folders). It stays outside the app — nothing is copied in.")
    c1, c2 = st.columns(2)
    if c1.button("Save & load", key="sp_save", width="stretch"):
        save_data_dir(os.path.expanduser(path.strip()))
        _load_cached.cache_clear()
        st.rerun()
    if c2.button("Reload", key="sp_reload", width="stretch"):
        _load_cached.cache_clear()
        st.rerun()
    if ok:
        st.caption(f"Rules (what counts as spending): `{os.path.join(data_dir, RULES_FILENAME)}`. "
                   "Edit it, then Reload.")
    st.caption(FORMATS_NOTE)


def _upload_panel(st, store: Dict) -> None:
    """Upload statements (and optionally a rules file) into this session only."""
    st.file_uploader(
        "Upload statements", type=["csv", "pdf", "json"], accept_multiple_files=True,
        key=_uploader_key(st), on_change=_take_uploads, args=(st,),
        help="Bank / card / Venmo statements (CSV or PDF). Optionally add your rules file "
             f"({RULES_FILENAME}, JSON) to tune what counts as spending; without one, generic "
             "rules apply. A file with the same name as an earlier one replaces it.")
    n = len(store["files"])
    if n or store["rules"]:
        rules = f"rules from {store['rules'][0]}" if store["rules"] else "default rules"
        st.caption(f"In this session: {n} statement file{'' if n == 1 else 's'}, {rules}.")
        st.button("Clear uploaded files", key="sp_clear", on_click=_clear_uploads, args=(st,),
                  width="stretch")
    st.caption(PRIVACY_NOTE)
    st.caption(FORMATS_NOTE)


def gap_notes(data: Dict) -> List[str]:
    """Plain-language list of missing data (empty when nothing is missing)."""
    notes = []
    for s in data["sources"]:
        if s["rows"] < 20:
            paid = (f" {money_md(s['paid_unitemized'])} was paid to it from your other accounts "
                    f"({_mon(s['paid_months'][0])} – {_mon(s['paid_months'][-1])}) and isn't itemized."
                    if s["paid_unitemized"] > 0 else "")
            notes.append(f"**{s['source']}**: only {s['rows']} transaction(s) loaded "
                         f"({_day(s['first'])} – {_day(s['last'])}).{paid} Export its full history.")
        for a, b in s["gaps"]:
            notes.append(f"**{s['source']}**: nothing from {_day(a)} to {_day(b)} — missing statements?")
        if s["empty_months"] and not s["gaps"]:
            notes.append(f"**{s['source']}**: nothing in {', '.join(_mon(p) for p in s['empty_months'])} "
                         "— missing statement?")
    notes += data["problems"]
    return notes


MA_CHOICES = {"Off": 0, "3 mo": 3, "6 mo": 6, "12 mo": 12}


def _md_day(ts: pd.Timestamp) -> str:
    return f"{ts:%b} {ts.day}, {ts.year}"


def _ranked_lists(st, tx: pd.DataFrame, start: pd.Period, end: pd.Period, category: str) -> None:
    """Two numbered, plain-text lists for one category: biggest purchases and
    most frequent merchants (easier to scan than a wide table)."""
    s = counted(tx)
    s = s[(s["month"] >= start) & (s["month"] <= end) & (s["category"] == category)]
    # Fixed monthly estimates are repeated placeholders, not purchases: leave them out.
    buys = s[(s["kind"] == "spend") & (s["amount"] < 0) & (s["account"] != ESTIMATE_SOURCE)]
    left, right = st.columns(2)
    with left:
        st.markdown("**Largest purchases**")
        top = buys.nlargest(10, "spend")
        st.markdown("\n".join(f"{i}. **{money_md(r.spend)}** · {_md_day(r.date)} — {r.merchant}"
                               for i, r in enumerate(top.itertuples(), 1)) or "_None in this period._")
    with right:
        st.markdown("**Most frequent merchants**")
        if buys.empty:
            st.markdown("_None in this period._")
        else:
            g = (buys.assign(_k=buys["description"].map(merchant_key))
                 .groupby("_k").agg(name=("merchant", lambda m: m.value_counts().index[0]),
                                    n=("spend", "size"), total=("spend", "sum"))
                 .sort_values(["n", "total"], ascending=False).head(10))
            st.markdown("\n".join(f"{i}. **{r.name}** — {r.n}× · {money_md(r.total)}"
                                   for i, r in enumerate(g.itertuples(), 1)))


def render(st, **_kwargs) -> None:
    hosted = is_hosted()
    data_dir = configured_data_dir()                 # always "" when hosted
    folder_ok = bool(data_dir) and os.path.isdir(data_dir)
    store = _upload_store(st)
    title, gear = st.columns([6, 1], vertical_alignment="bottom")
    title.markdown('<div class="mc-section">Spending</div>', unsafe_allow_html=True)
    if folder_ok:                                    # local folder: as before
        with gear.popover("Statements", width="stretch"):
            _settings_form(st, data_dir, True)
        data = load(data_dir)
    elif store["files"] or store["rules"]:
        # Panel first, so Clear stays reachable even if the files can't be processed.
        with gear.popover("Statements", width="stretch"):
            _upload_panel(st, store)
            _settings_form(st, data_dir, False)      # local only: can still pick a folder
        try:
            data = _uploaded_data(st)
        except Exception as exc:  # untrusted files must not take the tab down
            st.error(f"These files couldn't be processed ({type(exc).__name__}: {exc}). "
                     "Clear them under Statements and try again.")
            return
        if data["rules_error"]:
            st.warning(data["rules_error"])
    else:
        st.info("Upload your bank, card and Venmo statements to see your spending." if hosted
                else "Choose the folder holding your statements, or upload them, to see your spending.")
        _settings_form(st, data_dir, False)          # renders nothing when hosted
        _upload_panel(st, store)
        return
    tx = data["tx"]
    if tx.empty:
        st.info("No supported statements found " + ("in that folder." if folder_ok
                                                    else "in the uploaded files."))
        if data["problems"]:
            st.warning("Skipped:\n\n- " + "\n- ".join(data["problems"]))
        return
    complete = data["complete"]
    months = sorted(tx["month"].unique())
    incomplete = [m for m in pd.period_range(months[0], months[-1], freq="M") if m not in complete]
    dark = is_dark(st)
    overrides = st.session_state.get("user_overrides", {}) or {}

    # ---- controls: one place, and every number below follows them
    c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
    with c1:
        choice = st.segmented_control("Period", PERIODS, default=PERIODS[0], key="sp_period") or PERIODS[0]
    with c2:
        ma_label = st.segmented_control("Moving average", list(MA_CHOICES), default="3 mo",
                                        key="sp_ma") or "Off"
    window = MA_CHOICES[ma_label]
    c3, c4 = st.columns([4, 1.4], vertical_alignment="bottom")
    with c3:
        sel = st.pills("Include", GROUPS, selection_mode="multi", default=GROUPS, key="sp_groups") or []
    with c4:
        drop_oneoffs = st.toggle(f"Hide one-offs ({money_md(ONE_OFF)}+)", key="sp_oneoffs",
                                 help="Hide single purchases of $500 or more (and paybacks for "
                                      "them) to see routine spending.")
    if not sel:
        st.info("Pick at least one expense category under Include.")
        return
    start, end = period_bounds(months, complete, choice)
    view = apply_filters(tx, sel, drop_oneoffs)
    tiny = tuple(x["source"] for x in data["sources"] if x["paid_unitemized"] > 0)
    k = kpis(view, start, end, complete, tiny)
    good = [m for m in complete if start <= m <= end]
    plan = compute_expenses_today(overrides)
    housing_now = current_housing(tx, complete)
    housing = k["per_month"] - k["per_month_ex_housing"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Housing", money(housing) if "Housing" in sel else "—",
              help=f"Average per complete month, {_mon(start)} – {_mon(end)}. Your current "
                   f"payment is {money_md(housing_now)}/month; Plan vs. actual uses that.")
    m2.metric("Everything else", money(k["per_month_ex_housing"]),
              help=f"Average per complete month, {_mon(start)} – {_mon(end)}, after paybacks.")
    m3.metric("Total per month", money(k["per_month"]))
    est = view[(view["source"] == ESTIMATE_SOURCE) & view["month"].isin(good)]
    est_month = est["spend"].sum() / max(len(good), 1)
    m4.metric("Total per year", money(k["per_month"] * 12),
              help=(f"Includes {money_md(est_month)}/month of fixed estimates (not from statements). "
                    if est_month else "Your accounts only. ")
                   + f"The plan's spending input is {money_md(plan)}/yr.")
    line = [f"{len(good)} complete months, {_mon(start)} – {_mon(end)}",
            f"current housing payment {money_md(housing_now)}/mo"]
    if est_month:
        names = ", ".join(sorted(set(est["description"])))
        line.append(f"{names} {money_md(est_month)}/mo is a fixed estimate (hatched)")
    if len(sel) < len(GROUPS) or drop_oneoffs:
        line.append(f"showing {len(sel)} of {len(GROUPS)} categories"
                    + (", one-offs left out" if drop_oneoffs else ""))
    line.append(f"not counted: {money_md(k['work_travel'])} work travel, "
                f"{money_md(k['bought_for_others'])} bought for others")
    if k["unitemized_per_month"] > 0:
        line.append(f"up to {money_md(k['unitemized_per_month'])}/mo to {', '.join(tiny)} not itemized")
    notes = gap_notes(data)
    if notes:
        line.append(f"⚠ {len(notes)} data gap{'s' if len(notes) > 1 else ''} — see Data")
    st.caption(" · ".join(line))

    sig_last = [x["last"] for x in data["sources"] if x["rows"] >= 20]
    chart_end = max(end, min(sig_last).to_period("M")) if sig_last else end
    t_over, t_trend, t_tx, t_data = st.tabs(["Overview", "Trends", "Transactions", "Data"])

    with t_over:
        left, right = st.columns(2)
        with left:
            st.markdown("**Your average month**")
            avg = group_averages(view, good)
            _chart(st, lambda compact: pie_figure(avg, dark, compact), "sp_avg_donut",
                   {"displayModeBar": False})
        with right:
            st.markdown("**Plan vs. actual**")
            # Not the period picker's window: the same figures "Use my actual
            # spending" copies, so after a click every difference is zero.
            g = plan_vs_actual(overrides, session_actual(st, data), sel)

            def _or_dash(fmt):
                return lambda v: "—" if pd.isna(v) else fmt(v)
            st.dataframe(pd.DataFrame({
                "Expense category": g["Expense category"],
                "Your plan": g["Your plan"].map(money),
                "Actual": g["Actual"].map(_or_dash(money)),
                "Difference": g["Difference"].map(_or_dash(lambda v: ("+" if v > 0 else "") + money(v))),
            }), hide_index=True, width="stretch")
            no_partner = ((g["Expense category"] == "Partner spending") & g["Actual"].isna()
                          & (g["Your plan"] > 0)).any()
            st.caption("Plan = the Expenses section's monthly inputs. Actual = your accounts averaged "
                       "over every complete month (not just the period above), after paybacks; "
                       "housing is your current payment."
                       + (" Partner spending isn't in your statements, so the plan keeps its own "
                          "figure." if no_partner else ""))
            sync_control(st, data, "sp_use_actual")
        st.markdown("**Spending by month**")
        first = min(complete[0], start) if complete else start
        full = monthly_table(view, first, chart_end, sel)
        table = full.loc[start:chart_end]
        ma = moving_average(full["Net"], complete, window) if window else None
        _chart(st, lambda compact: monthly_figure(table, incomplete, dark, ma, window, compact),
               "sp_monthly", PLOTLY_CONFIG)
        st.caption("Each bar is your real share: purchases minus refunds and minus what people paid "
                   "you back. The average skips shaded months (missing statements).")

    with t_trend:
        choices = list(sel)
        # Start on something that varies: housing is a flat payment.
        first = next((c for c in choices if c != "Housing"), choices[0])
        pick = st.pills("Expense category", choices, default=first, key="sp_cat",
                        label_visibility="collapsed") or first
        _chart(st, lambda compact: category_trend_figure(view, pick, start, chart_end, incomplete,
                                                         dark, window, compact),
               "sp_cat_trend", PLOTLY_CONFIG)
        a, b = st.columns(2)
        with a:
            st.markdown(f"**Top merchants — {pick}**")
            st.dataframe(_merchants_per_year(view, start, end, complete, pick, 10)
                         .assign(**{"Per year": lambda d: d["Per year"].map(money)}),
                         hide_index=True, width="stretch")
        with b:
            st.markdown("**Inside this expense category**")
            summary = category_summary(view, start, end, complete)
            det = summary.reset_index().rename(columns={"category": "Category"})
            st.dataframe(det[det["Expense category"] == pick][["Category", "Per month", "Per year"]]
                         .assign(**{"Per month": lambda d: d["Per month"].map(money),
                                    "Per year": lambda d: d["Per year"].map(money)}),
                         hide_index=True, width="stretch")
        st.caption("Per year over complete months. Merchant totals are before paybacks; categories are after.")

    with t_tx:
        cats = category_table(view, start, end)
        st.markdown("**By category**")
        st.dataframe(cats.assign(**{c: cats[c].map(money) for c in ("Total", "Average", "Largest")}),
                     hide_index=True, width="stretch",
                     height=min(36 * (len(cats) + 1) + 2, 420))
        if not cats.empty:
            labels = {f"{r.Category} · {r.Transactions}": r.Category for r in cats.itertuples()}
            first = next((lb for lb, c in labels.items() if c != "Housing"), list(labels)[0])
            pick_label = st.pills("Category", list(labels), default=first, key="sp_tx_cat",
                                  label_visibility="collapsed") or first
            _ranked_lists(st, view, start, end, labels[pick_label])
        st.markdown("**Search all transactions**")
        views = {"Counted": ["spend", "payback"], "Left out": ["excluded"],
                 "Transfers & income": ["transfer", "income"], "All": None}
        a, b = st.columns([3, 2], vertical_alignment="bottom")
        with a:
            kind_view = st.segmented_control("Show", list(views), default="Counted", key="sp_view") or "Counted"
        with b:
            q = st.text_input("Search", key="sp_q", placeholder="Search merchant, note, category…",
                              label_visibility="collapsed")
        rows = (view if kind_view == "Counted" else tx)
        rows = rows[(rows["month"] >= start) & (rows["month"] <= end)]
        if views[kind_view]:
            rows = rows[rows["kind"].isin(views[kind_view])]
        if q:
            hay = rows["description"] + " " + rows["category"] + " " + rows["reason"]
            rows = rows[hay.str.contains(q, case=False, regex=False)]
        plain = {"spend": "Counted", "payback": "Paid back to you", "excluded": "Left out",
                 "transfer": "Between accounts", "income": "Income"}
        show = rows.sort_values("date", ascending=False).assign(
            kind=lambda d: d["kind"].map(plain), cost=lambda d: -d["amount"])
        st.dataframe(show[["date", "merchant", "category", "kind", "reason", "cost"]],
                     hide_index=True, width="stretch", height=380,
                     column_config={"date": st.column_config.DateColumn("Date"),
                                    "merchant": "Description", "category": "Category",
                                    "kind": "Counted as", "reason": "Why",
                                    "cost": st.column_config.NumberColumn("Cost", format="dollar")})
        st.caption(f"{len(rows):,} rows. Cost is positive for money you spent, negative for money in.")

    with t_data:
        if notes:
            st.warning("Missing data:\n\n- " + "\n- ".join(notes))
        else:
            st.success("No missing statements in this period.")
        checks = data["checks"]
        bad = [c for c in checks if abs(c["expected"] - c["parsed"]) > 0.01]
        if checks and not bad:
            st.success(f"All {len(checks)} statement totals match what was read, to the cent.")
        elif bad:
            st.error("These statement totals don't match what was read:")
            st.dataframe(pd.DataFrame(bad), hide_index=True, width="stretch")
        st.markdown("**What was left out, and why**")
        out = tx[(tx["month"] >= start) & (tx["month"] <= end)
                 & tx["kind"].isin(["excluded", "transfer", "income"])]
        out = out.assign(kind=out["kind"].map({"excluded": "Left out", "transfer": "Between accounts",
                                               "income": "Income"}))
        why = (out.groupby(["kind", "reason"])["amount"].agg(["size", "sum"]).reset_index()
               .rename(columns={"kind": "Type", "reason": "Reason", "size": "Transactions",
                                "sum": "Net amount"}))
        why["Net amount"] = why["Net amount"].map(money)
        st.dataframe(why, hide_index=True, width="stretch")
        st.caption("Transfers move your own money between accounts (card payments, savings, Venmo "
                   "cash-outs); counting them would double count purchases.")
