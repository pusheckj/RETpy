"""Spending dashboard: parsers, classification, coverage and the tab itself.

All fixtures are SYNTHETIC — no real statements, names or amounts belong in this
package. The PDF parsers are tested on the text lines / positioned word rows
they consume, so no PDF files (or pymupdf) are needed here.
"""
import os
import sys
from datetime import datetime

import pandas as pd
import pytest

UI = os.path.join(os.path.dirname(__file__), "..", "ui")
sys.path.insert(0, UI)

from utils import spending_parsers as sp  # noqa: E402
from utils import spending_rules as sr  # noqa: E402
from components import spending_dashboard as sd  # noqa: E402


# ---------------------------------------------------------------- fixtures

ALLY_LINES = [
    "Ally Bank", "Account Number:  xxxxxx1111",
    "07/01/2026", "Beginning Balance", "$1,000.00",
    "07/03/2026", "ACH Withdrawal", "BIGBANK MORTGAGE~ Future", "Amount: 2000 ~ Tran: ACHDW",
    "$0.00", "-$2,000.00", "-$1,000.00",
    "07/05/2026", "ACH Withdrawal", "CARDMEMBER SERV WEB PYMT", "$0.00", "-$300.00", "-$1,300.00",
    "07/10/2026", "Direct Deposit", "ACME CORP PAYROLL", "$5,000.00", "-$0.00", "$3,700.00",
    "07/31/2026", "Interest Paid", " ", "$0.25", "-$0.00", "$3,700.25",
    "07/31/2026", "Ending Balance", "$3,700.25",
    "08/01/2026", "Page 2", "$1.00", "$2.00", "$3.00",   # page furniture, not a txn
]


def _elan(rows_spec, closing="01/27/2026", purchases=None, payments=None, credits=None):
    """Build (word_rows, lines) for a synthetic Elan statement.

    rows_spec: list of (y, [(x, word), ...]).
    """
    lines = [f"Open Date: 12/28/2025 Closing Date: {closing}", "Account ending in: 4321",
             "Fidelity® Rewards Visa Signature® Card", "Elan Financial Services"]
    for label, v in (("Purchases", purchases), ("Payments", payments), ("Other Credits", credits)):
        if v is not None:
            lines += [label, "+", f"${v:,.2f}"]
    return rows_spec, lines


def _row(y, *cells):
    """cells: (x, 'a b c') -> one token per word, spaced 8pt apart."""
    toks = []
    for x, text in cells:
        for i, w in enumerate(text.split()):
            toks.append((x + i * 8.0, w))
    return (float(y), toks)


VENMO_CSV = """Account Statement - (@Pat-Doe) ,,,,,,,,,
Account Activity,,,,,,,,,
,ID,Datetime,Type,Status,Note,From,To,Amount (total),Funding Source,Destination
,,,,,,,,,,
,1001,2026-07-02T10:00:00,Payment,Complete,Water,Sam Roe,Pat Doe,+ $40.00,,Venmo balance
,1002,2026-07-03T10:00:00,Payment,Complete,🍕,Pat Doe,Lee Poe,- $25.00,Bank *1111,
,1003,2026-07-04T10:00:00,Standard Transfer,Issued,,,,"- $1,050.00",,Bank *1111
,1004,2026-07-05T10:00:00,Payment,Complete,rent,Rae Tenant,Pat Doe,+ $900.00,,Venmo balance
,1005,2026-07-06T10:00:00,Payment,Complete,new tablet,Kim Buyer,Pat Doe,+ $450.00,,Venmo balance
,1006,2026-07-07T10:00:00,Payment,Failed,oops,Pat Doe,Lee Poe,- $5.00,Bank *1111,
,1007,2026-07-08T10:00:00,Payment,Complete,Thanks!,Jo Buyer,Pat Doe,+ $812.00,,Venmo balance
"""

FIDELITY_CSV = '''"Date","Transaction","Name","Memo","Amount"
"2026-07-02","DEBIT","GADGET.COM/US 800-000-0000 CA","1; 05732; ; ; ;","-450.00"
"2026-07-03","DEBIT","GADGET.COM/US 800-000-0000 CA","1; 05732; ; ; ;","-820.00"
"2026-07-04","DEBIT","BEAN CAFE 0012 ANYTOWN CA","1; 05814; ; ; ;","-9.00"
"2026-07-04","DEBIT","BEAN CAFE 0012 ANYTOWN CA","1; 05814; ; ; ;","-9.00"
"2026-07-06","DEBIT","GRAND HOTEL REMOTEVILLE CA","1; 07011; ; ; ;","-600.00"
"2026-07-07","DEBIT","EBAY O*123 REMOTEVILLE CA","1; 05999; ; ; ;","-50.00"
"2026-07-08","CREDIT","BEAN CAFE 0012 ANYTOWN CA","1; 05814; ; ; ;","4.00"
"2026-07-09","CREDIT","PAYMENT THANK YOU","WEB AUTOMTC; ; ; ; ;","300.00"
'''

APPLE_CARD_CSV = """Transaction Date,Clearing Date,Description,Merchant,Category,Type,Amount (USD),Purchased By
07/05/2026,07/05/2026,"CORNER MARKET","Corner Market","Grocery","Purchase","42.10","Pat Doe"
07/06/2026,07/06/2026,"ACH DEPOSIT INTERNET TRANSFER","Ach Deposit","Payment","Payment","-200.00","Pat Doe"
"""

PERSONAL_RULES = {
    "work_travel_locations": ["REMOTEVILLE"],
    "work_travel_exceptions": ["EBAY"],
    "excluded_purchase_patterns": [r"GADGET\.COM/US"],
    "excluded_payback_note_patterns": ["tablet"],
    "income_counterparties": {"Rae Tenant": "Rent"},
}


def _rules():
    r = sr.load_rules(None)
    for k, v in PERSONAL_RULES.items():
        r[k] = r[k] + v if isinstance(r[k], list) else {**r[k], **v}
    return r


def _all_rows():
    rows = sp.parse_fidelity_csv(FIDELITY_CSV, "fid.csv")
    rows += sp.parse_venmo_csv(VENMO_CSV, "venmo.csv")
    rows += sp.parse_ally_lines(ALLY_LINES, "ally.pdf")[0]
    df = pd.DataFrame(rows, columns=sp.COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------- parsers

class TestAlly:
    def test_rows_amounts_and_payee_first_descriptions(self):
        rows, _ = sp.parse_ally_lines(ALLY_LINES, "a.pdf")
        assert [r["amount"] for r in rows] == [-2000.0, -300.0, 5000.0, 0.25]
        assert rows[0]["description"] == "BIGBANK MORTGAGE | ACH Withdrawal"
        assert rows[3]["description"] == "Interest Paid"
        assert all(r["account"] == "Ally 1111" for r in rows)

    def test_balance_check_matches(self):
        _, checks = sp.parse_ally_lines(ALLY_LINES, "a.pdf")
        assert len(checks) == 1
        assert checks[0]["expected"] == pytest.approx(2700.25)
        assert checks[0]["parsed"] == pytest.approx(2700.25)

    def test_page_furniture_is_not_a_transaction(self):
        rows, _ = sp.parse_ally_lines(ALLY_LINES, "a.pdf")
        assert not any("Page" in r["description"] for r in rows)


class TestElan:
    def test_cr_marker_on_the_row_makes_a_credit(self):
        """The bug this parser exists to avoid: in the PDF text stream every 'CR'
        is batched at the section header, so payments read as purchases."""
        rows_spec, lines = _elan([
            _row(100, (64, "01/16"), (100, "01/16"), (136, "MTC"), (172, "PAYMENT THANK YOU"),
                 (474, "$1,234.56"), (514, "CR")),
            _row(120, (64, "01/20"), (100, "01/17"), (136, "0001"), (172, "HARDWARE STORE CA"),
                 (487, "$45.67")),
        ], payments=1234.56, purchases=45.67)
        rows, checks = sp.parse_elan_rows(rows_spec, lines, "e.pdf")
        assert [r["amount"] for r in rows] == [1234.56, -45.67]
        assert all(abs(c["expected"] - c["parsed"]) < 0.01 for c in checks)

    def test_itinerary_lines_join_and_totals_dont(self):
        rows_spec, lines = _elan([
            _row(100, (64, "01/18"), (100, "01/17"), (136, "0002"), (172, "SKY AIR 800 CA"),
                 (480, "$250.00")),
            _row(110, (172, "DOE/PAT 02/20/26")),
            _row(120, (172, "SPRINGFIELD TO SHELBYVILLE")),
            _row(140, (352, "TOTAL THIS PERIOD"), (474, "$250.00")),
        ], purchases=250.00)
        rows, checks = sp.parse_elan_rows(rows_spec, lines, "e.pdf")
        assert len(rows) == 1
        assert rows[0]["description"] == "SKY AIR 800 CA | DOE/PAT 02/20/26 | SPRINGFIELD TO SHELBYVILLE"
        assert checks[0]["parsed"] == pytest.approx(250.00)

    def test_amount_on_continuation_row(self):
        rows_spec, lines = _elan([
            _row(100, (64, "01/26"), (136, "0003"), (172, "ACME CR SUPPLY # 0042")),
            _row(110, (172, "CREDIT ADJUSTMENT"), (480, "$120.00"), (514, "CR")),
        ])
        rows, _ = sp.parse_elan_rows(rows_spec, lines, "e.pdf")
        assert rows[0]["amount"] == 120.00
        assert "CREDIT ADJUSTMENT" in rows[0]["description"]

    def test_year_rolls_back_across_new_year(self):
        rows_spec, lines = _elan([
            _row(100, (64, "12/30"), (100, "12/29"), (136, "0001"), (172, "SHOP"), (480, "$5.00")),
            _row(120, (64, "01/02"), (100, "01/02"), (136, "0002"), (172, "SHOP"), (480, "$6.00")),
        ], closing="01/27/2026")
        rows, _ = sp.parse_elan_rows(rows_spec, lines, "e.pdf")
        assert rows[0]["date"] == datetime(2025, 12, 30)        # POST date, like card CSVs
        assert rows[1]["date"] == datetime(2026, 1, 2)

    def test_mismatch_is_reported(self):
        rows_spec, lines = _elan([
            _row(100, (64, "01/20"), (100, "01/17"), (136, "0001"), (172, "SHOP"), (487, "$10.00")),
        ], purchases=99.00)
        _, checks = sp.parse_elan_rows(rows_spec, lines, "e.pdf")
        assert checks[0]["expected"] == 99.00 and checks[0]["parsed"] == 10.00

    def test_word_rows_groups_the_lower_cr(self):
        words = [(64, 100.0, 0, 0, "01/16"), (474, 100.0, 0, 0, "$5.00"), (514, 101.8, 0, 0, "CR"),
                 (64, 120.0, 0, 0, "01/17")]
        rows = sp._word_rows(words)
        assert [[t for _, t in r] for _, r in rows] == [["01/16", "$5.00", "CR"], ["01/17"]]


class TestCsvParsers:
    def test_venmo_self_counterparty_and_failed_skipped(self):
        rows = sp.parse_venmo_csv(VENMO_CSV, "v.csv")
        assert len(rows) == 6                                   # failed row dropped
        by_ref = {r["ref"]: r for r in rows}
        assert by_ref["1001"]["counterparty"] == "Sam Roe"      # money in: From
        assert by_ref["1002"]["counterparty"] == "Lee Poe"      # money out: To
        assert by_ref["1002"]["amount"] == -25.0
        assert by_ref["1003"]["amount"] == -1050.0
        assert by_ref["1001"]["description"].startswith("Sam Roe — Water")

    def test_fidelity_mcc(self):
        rows = sp.parse_fidelity_csv(FIDELITY_CSV, "f.csv")
        assert rows[0]["mcc"] == "05732" and rows[0]["amount"] == -450.0

    def test_apple_card_sign_flipped(self):
        rows = sp.parse_apple_card_csv(APPLE_CARD_CSV, "a.csv")
        assert [r["amount"] for r in rows] == [-42.10, 200.0]
        assert rows[0]["raw_category"] == "Grocery"


class TestDedupe:
    def test_overlapping_files_collapse_but_same_day_repeats_stay(self):
        a = sp.parse_fidelity_csv(FIDELITY_CSV, "a.csv")
        b = sp.parse_fidelity_csv(FIDELITY_CSV, "b.csv")       # same statement twice
        df = pd.DataFrame(a + b, columns=sp.COLUMNS)
        df["date"] = pd.to_datetime(df["date"])
        out = sp.dedupe(df)
        assert len(out) == len(a)
        # the two identical $9 coffees on 07/04 are both real
        assert (out["amount"] == -9.0).sum() == 2

    def test_venmo_dedupes_on_id(self):
        rows = sp.parse_venmo_csv(VENMO_CSV, "a.csv") + sp.parse_venmo_csv(VENMO_CSV, "b.csv")
        df = pd.DataFrame(rows, columns=sp.COLUMNS)
        df["date"] = pd.to_datetime(df["date"])
        assert len(sp.dedupe(df)) == 6


# ---------------------------------------------------------------- classification

class TestClassify:
    @pytest.fixture
    def c(self):
        return sr.classify(_all_rows(), _rules())

    def _one(self, c, needle):
        rows = c[c["description"].str.contains(needle, regex=False)]
        assert len(rows) >= 1, needle
        return rows

    def test_card_payment_counted_once(self, c):
        """The bank paying the card and the card's 'PAYMENT THANK YOU' are both
        transfers, so only the card's purchases count."""
        assert set(self._one(c, "CARDMEMBER SERV")["kind"]) == {"transfer"}
        assert set(self._one(c, "PAYMENT THANK YOU")["kind"]) == {"transfer"}
        assert set(self._one(c, "Standard Transfer")["kind"]) == {"transfer"}

    def test_net_spending_conserves_dollars(self, c):
        """Counted = mortgage + 2 coffees − coffee refund + eBay + Venmo 🍕 −
        payback for water. Nothing else may leak in."""
        net = c.loc[c["kind"].isin(["spend", "payback"]), "spend"].sum()
        assert net == pytest.approx(2000 + 9 + 9 - 4 + 50 + 25 - 40)

    def test_work_travel_excluded_with_exception(self, c):
        assert set(self._one(c, "GRAND HOTEL")["reason"]) == {sr.REASON_WORK_TRAVEL}
        assert set(self._one(c, "EBAY")["kind"]) == {"spend"}       # HQ'd there, still yours

    def test_bought_for_others_and_their_paybacks_excluded(self, c):
        assert set(self._one(c, "GADGET.COM")["reason"]) == {sr.REASON_BOUGHT_FOR_OTHERS}
        tablet = self._one(c, "new tablet")
        assert set(tablet["reason"]) == {sr.REASON_PAID_BACK_FOR_OTHERS}     # by note

    def test_unlabelled_payback_matched_by_amount(self, c):
        """'Thanks!' $812 doesn't say what it's for, but it's within 2% of an
        excluded $820 purchase days earlier, so it must not cancel real spending."""
        assert set(self._one(c, "Thanks!")["reason"]) == {sr.REASON_PAID_BACK_FOR_OTHERS}

    def test_rent_is_income_not_a_payback(self, c):
        rent = self._one(c, "Rae Tenant")
        assert set(rent["kind"]) == {"income"} and set(rent["reason"]) == {"Rent"}

    def test_payback_subtracts_in_its_category(self, c):
        water = self._one(c, "Sam Roe")
        assert set(water["kind"]) == {"payback"}
        assert water["category"].iloc[0] == "Utilities"
        assert water["spend"].iloc[0] == -40.0

    def test_refund_is_negative_spend_in_merchant_category(self, c):
        refund = c[(c["description"].str.contains("BEAN CAFE")) & (c["amount"] > 0)]
        assert refund["kind"].iloc[0] == "spend"
        assert refund["category"].iloc[0] == "Dining"
        assert refund["spend"].iloc[0] == -4.0

    def test_income_rows(self, c):
        assert set(self._one(c, "PAYROLL")["reason"]) == {"Payroll"}
        assert set(self._one(c, "Interest Paid")["reason"]) == {"Interest"}

    def test_learned_category_from_mcc(self):
        """A merchant seen with an MCC on a CSV keeps that category on a PDF row
        (no MCC). 'ZORBLAX' matches no keyword, so only learning can place it."""
        df = _all_rows()
        csv_row = df.iloc[[2]].copy()                       # MCC 05814 (fast food)
        csv_row["description"] = "ZORBLAX 0012 ANYTOWN CA"
        pdf_row = csv_row.copy()
        pdf_row["mcc"], pdf_row["file"] = "", "x.pdf"
        pdf_row["description"] = "ZORBLAX 0099 ANYTOWN CA"
        alone = sr.classify(pd.concat([df, pdf_row], ignore_index=True), _rules())
        assert alone.iloc[-1]["category"] == "Other"
        out = sr.classify(pd.concat([df, csv_row, pdf_row], ignore_index=True), _rules())
        assert out.iloc[-1]["category"] == "Dining"

    def test_personal_rules_merge(self, tmp_path):
        p = tmp_path / "rules.json"
        p.write_text('{"work_travel_locations": ["X"], "income_counterparties": {"A": "Rent"}, '
                     '"not_a_key": 1}', encoding="utf-8")
        r = sr.load_rules(str(p))
        assert r["work_travel_locations"] == ["X"]
        assert r["income_counterparties"] == {"A": "Rent"}
        assert "not_a_key" not in r
        assert r["transfer_patterns"] == sr.DEFAULT_RULES["transfer_patterns"]


# ---------------------------------------------------------------- coverage

class TestCoverage:
    def _df(self, dates, source="Card"):
        return pd.DataFrame({"date": pd.to_datetime(dates), "source": source})

    def test_gap_in_daily_source_marks_months_incomplete(self):
        days = list(pd.date_range("2026-01-01", "2026-02-10")) + \
               list(pd.date_range("2026-03-20", "2026-05-31"))
        _, complete = sp.coverage(self._df(days))
        assert [str(p) for p in complete] == ["2026-01", "2026-04", "2026-05"]

    def test_tiny_source_ignored_and_span_enforced(self):
        card = self._df(pd.date_range("2026-01-01", "2026-04-30"))
        bank = self._df(pd.date_range("2026-02-01", "2026-04-30", freq="3D"), "Bank")
        tiny = self._df(["2026-06-15"], "Tiny")
        _, complete = sp.coverage(pd.concat([card, bank, tiny]))
        # Jan lacks the bank; Jun has only the tiny source's single row.
        assert [str(p) for p in complete] == ["2026-02", "2026-03", "2026-04"]


# ---------------------------------------------------------------- dashboard

def _dash_tx():
    c = sr.classify(_all_rows(), _rules())
    c["month"] = c["date"].dt.to_period("M")
    c["merchant"] = c["description"].str.split(" | ", regex=False).str[0]
    return c


class TestDashboardSummaries:
    def test_period_ends_at_last_complete_month(self):
        months = list(pd.period_range("2025-01", "2026-09", freq="M"))
        complete = [m for m in months if str(m) != "2026-09"]
        start, end = sd.period_bounds(months, complete, "Last 12 months")
        assert (str(start), str(end)) == ("2025-09", "2026-08")
        assert str(sd.period_bounds(months, complete, "Year to date")[0]) == "2026-01"

    def test_averages_use_complete_months_only(self):
        tx = _dash_tx()
        jul = pd.Period("2026-07", "M")
        k_full = sd.kpis(tx, jul, jul, [jul])
        k_none = sd.kpis(tx, jul, jul, [])
        assert k_full["per_month"] == pytest.approx(2049.0)
        assert k_none["months"] == 0 and k_none["per_month"] == 0.0
        assert k_full["work_travel"] == pytest.approx(600.0)
        assert k_full["bought_for_others"] == pytest.approx(1270.0)

    def test_monthly_table_uses_expense_categories(self):
        tx = _dash_tx()
        jul = pd.Period("2026-07", "M")
        t = sd.monthly_table(tx, jul, jul)
        assert list(t.columns) == sd.GROUPS + ["Net"]
        row = t.loc[jul]
        assert row["Housing"] == pytest.approx(2000.0)
        assert row["Food & groceries"] == pytest.approx(39.0)          # 2 coffees - refund + Venmo 🍕
        assert row["Utilities"] == pytest.approx(-40.0)                # water payback netted in
        assert row["Entertainment / discretionary"] == pytest.approx(50.0)
        assert row["Net"] == pytest.approx(sd.kpis(tx, jul, jul, [jul])["per_month"])

    def test_housing_toggle(self):
        tx = _dash_tx()
        jul = pd.Period("2026-07", "M")
        t = sd.monthly_table(tx, jul, jul, [g for g in sd.GROUPS if g != 'Housing'])
        assert "Housing" not in t.columns
        assert t.loc[jul, "Net"] == pytest.approx(2049.0 - 2000.0)

    def test_top_merchants_group_by_payee(self):
        m = sd.top_merchants(_dash_tx(), pd.Period("2026-07", "M"), pd.Period("2026-07", "M"))
        assert m.iloc[0]["Merchant"] == "BIGBANK MORTGAGE"
        cafe = m[m["Merchant"].str.startswith("BEAN CAFE")]
        assert cafe["Total"].iloc[0] == pytest.approx(14.0) and cafe["Visits"].iloc[0] == 3

    def test_figures_build(self):
        tx = _dash_tx()
        jul = pd.Period("2026-07", "M")
        sd.monthly_figure(sd.monthly_table(tx, jul, jul), [jul], dark=False)
        sd.category_trend_figure(tx, "Food & groceries", jul, jul, [], dark=False)


class TestPrivacy:
    def test_settings_live_outside_the_package(self):
        pkg = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        assert not os.path.abspath(sd.SETTINGS_PATH).startswith(pkg)

    def test_env_var_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")       # local mode (hosted ignores it)
        monkeypatch.setenv("SPENDING_DATA_DIR", str(tmp_path))
        assert sd.configured_data_dir() == str(tmp_path)

    def test_no_personal_rules_ship_in_code(self):
        """Work-travel places, who pays rent, employer deposits: rules JSON only."""
        r = sr.DEFAULT_RULES
        for key in ("work_travel_locations", "work_travel_exceptions",
                    "excluded_purchase_patterns", "excluded_payback_note_patterns",
                    "reimbursement_patterns", "transfer_counterparties"):
            assert r[key] == [], key
        assert r["income_counterparties"] == {} and r["merchant_categories"] == {}


def test_tab_renders_end_to_end(tmp_path, monkeypatch):
    """Run the real component in Streamlit's AppTest against a synthetic folder."""
    from streamlit.testing.v1 import AppTest
    (tmp_path / "card").mkdir()
    (tmp_path / "card" / "fid.csv").write_text(FIDELITY_CSV, encoding="utf-8")
    (tmp_path / "venmo.csv").write_text(VENMO_CSV, encoding="utf-8")
    (tmp_path / "apple.csv").write_text(APPLE_CARD_CSV, encoding="utf-8")
    monkeypatch.setenv("RETIREMENT_SIM_HOSTED", "0")           # folder mode is local-only
    monkeypatch.setenv("SPENDING_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SPENDING_TEST_UI_DIR", os.path.abspath(UI))

    def _script():
        import os
        import sys
        sys.path.insert(0, os.environ["SPENDING_TEST_UI_DIR"])
        import streamlit as st
        from components import spending_dashboard
        spending_dashboard.render(st)

    at = AppTest.from_function(_script, default_timeout=60).run()
    assert not at.exception, at.exception
    labels = [m.label for m in at.metric]
    assert {"Housing", "Everything else", "Total per month", "Total per year"} <= set(labels)
    assert any("Apple Card" in w.value for w in at.warning)          # tiny source flagged


def test_ally_payee_drops_repeats_and_split_amount_noise():
    lines = ["Account Number:  xxxxxx2222",
             "07/03/2026", "ACH Withdrawal", "CITY WATER BILL~ Future Amount: 75.00 ~", "Tran: ACHDW",
             " WATER BILL", "$0.00", "-$75.00", "$925.00"]
    rows, _ = sp.parse_ally_lines(lines, "a.pdf")
    assert rows[0]["description"] == "CITY WATER BILL | ACH Withdrawal"


def test_housing_toggle_never_repaints_survivors():
    """'Color follows the entity': each expense bucket keeps one fixed color."""
    tx = _dash_tx()
    jul = pd.Period("2026-07", "M")
    on = {t.name: t.marker.color for t in sd.monthly_figure(sd.monthly_table(tx, jul, jul), [], False).data
          if t.type == "bar"}
    off = {t.name: t.marker.color for t in
           sd.monthly_figure(sd.monthly_table(tx, jul, jul, [g for g in sd.GROUPS if g != 'Housing']), [], False).data
           if t.type == "bar"}
    assert "Housing" in on and "Housing" not in off
    assert all(on[g] == off[g] for g in off)


def test_every_category_maps_to_an_expense_bucket():
    mapped = {c for _, _, cats in sd.EXPENSE_GROUPS for c in cats}
    assert set(sr.CATEGORIES) <= mapped


def test_buckets_and_inputs_come_from_one_list():
    """The tab's buckets, the Expenses inputs and the widget sync share one list,
    so a category can't exist on one screen and not the other."""
    from utils import expense_categories as ec
    from utils.widget_sync import DIRECT_MAPPINGS
    assert [g for g, _, _ in sd.EXPENSE_GROUPS] == [ec.HOUSING] + [c.label for c in ec.CATEGORIES]
    for c in ec.CATEGORIES:
        assert DIRECT_MAPPINGS[c.widget][0] == c.key
    for key, (widget, _max) in ec.INPUTS.items():
        assert DIRECT_MAPPINGS[widget][0] == key
    src = open(os.path.join(UI, "components", "sec_expenses.py"), encoding="utf-8").read()
    assert "for c in CATEGORIES" in src


def test_actual_plan_per_input():
    tx = _dash_tx()
    jul = pd.Period("2026-07", "M")
    a = sd.actual_plan(tx, [jul])
    assert a["MORTGAGE_MONTHLY"] == 2000 and "SPEND_RENT_MONTHLY" not in a
    assert a["SPEND_FOOD_MONTHLY"] == 39 and a["SPEND_DISCRETIONARY_MONTHLY"] == 50
    assert a["SPEND_UTILITIES_MONTHLY"] == 0              # paybacks beat bills: inputs can't go negative
    assert "PARTNER_OTHER_MONTHLY" not in a               # no estimate in the statements
    renter = sd.actual_plan(tx, [jul], owns=False)
    assert renter["SPEND_RENT_MONTHLY"] == 2000 and "MORTGAGE_MONTHLY" not in renter
    assert sd.plan_monthly({"SPEND_RENT_MONTHLY": 1800}, "Housing") == 1800.0


def test_actual_plan_uses_every_complete_month_not_the_period():
    rows = [{"date": "2026-06-05", "source": "Card", "description": "CAFE ONE", "mcc": "05814", "amount": -100},
            {"date": "2026-07-05", "source": "Card", "description": "CAFE ONE", "mcc": "05814", "amount": -300}]
    tx = sr.classify(_frame(rows), sr.load_rules(None))
    tx["month"] = tx["eff_date"].dt.to_period("M"); tx["merchant"] = tx["description"]
    jun, jul = pd.Period("2026-06", "M"), pd.Period("2026-07", "M")
    assert sd.actual_plan(tx, [jun, jul])["SPEND_FOOD_MONTHLY"] == 200


def test_plan_vs_actual_and_what_differs():
    tx = _dash_tx()
    jul = pd.Period("2026-07", "M")
    a = sd.actual_plan(tx, [jul])
    ov = {"MORTGAGE_MONTHLY": 2100, "SPEND_FOOD_MONTHLY": 100, "PARTNER_OTHER_MONTHLY": 1500}
    g = sd.plan_vs_actual(ov, a).set_index("Expense category")
    assert (g.loc["Housing", "Your plan"], g.loc["Housing", "Actual"]) == (2100.0, 2000.0)
    assert g.loc["Food & groceries", "Difference"] == pytest.approx(-61.0)
    assert pd.isna(g.loc["Partner spending", "Actual"])   # not in statements: never "differs"
    assert sd.differing(ov, a) == ["Housing", "Food & groceries", "Entertainment / discretionary"]
    assert sd.differing({**ov, **a}, a) == []
    assert list(sd.plan_vs_actual(ov, a, ["Housing"])["Expense category"]) == ["Housing"]


def test_use_actual_sets_plan_mirrors_and_inputs():
    class _St:
        session_state = {"user_overrides": {"SPEND_FOOD_MONTHLY": 1}}
    a = {"MORTGAGE_MONTHLY": 2000, "SPEND_UTILITIES_MONTHLY": 120, "PARTNER_OTHER_MONTHLY": 1900}
    sd.use_actual(_St, a)
    ov, ss = _St.session_state["user_overrides"], _St.session_state
    assert ov["MORTGAGE_MONTHLY"] == 2000 and ss["se_mortgage_monthly"] == 2000
    assert ov["UTILITIES_MONTHLY"] == 120 and ss["se_utilities"] == 120
    assert ov["PARTNER_MONTHLY_SPENDING"] == 1900 and ss["se_partner"] == 1900
    assert ov["SPEND_FOOD_MONTHLY"] == 1                  # untouched: not in ``actual``


def test_actual_plan_keeps_each_input_in_range():
    tx = _dash_tx()
    jul = pd.Period("2026-07", "M")
    big = tx.assign(spend=tx["spend"] * 100, amount=tx["amount"] * 100)
    assert sd.actual_plan(big, [jul])["MORTGAGE_MONTHLY"] == 20_000


# ---------------------------------------------------------------- gap & trip-day guards

def _frame(rows):  # noqa: E302
    df = pd.DataFrame([{**{c: "" for c in sp.COLUMNS}, **r} for r in rows], columns=sp.COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float)
    return df


def test_trip_day_rideshare_excluded_only_on_trip_days():
    rules = _rules()
    rules["work_trip_day_patterns"] = [r"\bUBER\b(?! ?EATS)", "AIRPORT"]
    df = _frame([
        {"date": "2026-07-06", "source": "Card", "description": "GRAND HOTEL REMOTEVILLE CA", "amount": -300},
        {"date": "2026-07-07", "source": "Card", "description": "UBER *TRIP HELP.UBER.COM CA", "amount": -30},
        {"date": "2026-07-07", "source": "Card", "description": "CORNER GROCER ANYTOWN CA", "amount": -40},
        {"date": "2026-07-20", "source": "Card", "description": "UBER *TRIP HELP.UBER.COM CA", "amount": -25},
        {"date": "2026-07-06", "source": "Card", "description": "UBER EATS PENDING", "amount": -15},
    ])
    out = sr.classify(df, rules).set_index("description")
    assert out.loc["UBER *TRIP HELP.UBER.COM CA", "reason"].tolist() == [sr.REASON_TRIP_EXTRA, ""]
    assert out.loc["CORNER GROCER ANYTOWN CA", "kind"] == "spend"        # same day, not a trip cost
    assert out.loc["UBER EATS PENDING", "kind"] == "spend"                 # food delivery ≠ ride


def test_quiet_sparse_month_is_not_missing_unless_bank_shows_activity():
    venmo = [{"date": f"2026-{m:02d}-10", "source": "Venmo", "description": "x", "amount": -5}
             for m in (1, 2, 3, 5, 6) for _ in range(5)]                    # nothing in April
    bank = [{"date": d, "source": "Bank", "description": "rent", "amount": -1}
            for d in pd.date_range("2026-01-01", "2026-06-30", freq="2D").strftime("%Y-%m-%d")]
    _, complete = sp.coverage(_frame(venmo + bank))
    assert "2026-04" in [str(p) for p in complete]                          # genuinely quiet
    funded = bank + [{"date": "2026-04-12", "source": "Bank", "description": "VENMO PAYMENT",
                      "amount": -50}]
    _, complete = sp.coverage(_frame(venmo + funded))
    assert "2026-04" not in [str(p) for p in complete]                      # statement missing


def test_tiny_source_reports_unitemized_payments():
    bank = [{"date": d, "source": "Bank", "description": "rent", "amount": -1}
            for d in pd.date_range("2026-01-01", "2026-03-31", freq="2D").strftime("%Y-%m-%d")]
    bank += [{"date": "2026-02-05", "source": "Bank", "description": "APPLECARD GSBANK PAYMENT",
              "amount": -80}]
    tiny = [{"date": "2026-03-04", "source": "Apple Card", "description": "x", "amount": -1}]
    sources, _ = sp.coverage(_frame(bank + tiny))
    apple = next(s for s in sources if s["source"] == "Apple Card")
    assert apple["paid_unitemized"] == 80.0
    assert [str(m) for m in apple["paid_months"]] == ["2026-02"]


def test_summaries_never_sum_over_incomplete_months():
    tx = _dash_tx()
    jul, aug = pd.Period("2026-07", "M"), pd.Period("2026-08", "M")
    extra = tx.iloc[[0]].copy()
    extra["month"], extra["date"] = aug, pd.Timestamp("2026-08-05")
    extra["kind"], extra["category"], extra["spend"], extra["amount"] = "spend", "Dining", 9999.0, -9999.0
    both = pd.concat([tx, extra], ignore_index=True)
    s = sd.category_summary(both, jul, aug, complete=[jul])                  # Aug incomplete
    assert s.loc["Dining", "Per month"] == pytest.approx(39.0)
    m = sd.top_merchants(both, jul, aug, complete=[jul])
    assert m["Total"].max() < 9999.0


def test_kpis_report_unitemized_card_payments():
    tx = _dash_tx()
    jul = pd.Period("2026-07", "M")
    row = tx.iloc[[0]].copy()
    row["description"], row["kind"], row["amount"] = "APPLECARD GSBANK PAYMENT | ACH", "transfer", -80.0
    k = sd.kpis(pd.concat([tx, row], ignore_index=True), jul, jul, [jul], ("Apple Card",))
    assert k["unitemized_per_month"] == pytest.approx(80.0)
    assert sd.kpis(tx, jul, jul, [jul])["unitemized_per_month"] == 0.0



def test_same_purchase_in_csv_and_pdf_counted_once_keeping_mcc():
    """CSV exports date by POSTING; the PDF row must use its post date too, or
    the overlap double counts. The CSV copy (with MCC) is the one kept."""
    rows_spec, lines = _elan([
        _row(100, (64, "01/20"), (100, "01/17"), (136, "0001"), (172, "HARDWARE STORE CA"),
             (487, "$45.67")),
    ], purchases=45.67)
    pdf_rows, _ = sp.parse_elan_rows(rows_spec, lines, "a.pdf")
    csv_rows = sp.parse_fidelity_csv(
        '"Date","Transaction","Name","Memo","Amount"\n'
        '"2026-01-20","DEBIT","HARDWARE STORE   CA","1; 05200; ; ; ;","-45.67"\n', "b.csv")
    df = pd.DataFrame(pdf_rows + csv_rows, columns=sp.COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    out = sp.dedupe(df)
    assert len(out) == 1
    assert out.iloc[0]["mcc"] == "05200"


def test_cr_inside_a_description_is_kept():
    rows_spec, lines = _elan([
        _row(100, (64, "09/28"), (136, "0003"), (172, "ACME CR SUPPLY # 0042"),
             (480, "$120.00"), (514, "CR")),
    ], closing="09/28/2026")
    rows, _ = sp.parse_elan_rows(rows_spec, lines, "e.pdf")
    assert rows[0]["description"] == "ACME CR SUPPLY # 0042" and rows[0]["amount"] == 120.0


def test_pdf_continuation_lines_dont_break_dedupe():
    """'HOTEL EXAMPLE SPRINGFIELD IL | FOLIO: 123456' (PDF) is the same stay as the CSV's
    'HOTEL EXAMPLE SPRINGFIELD IL' — the continuation line must not leak into the key."""
    df = _frame([
        {"date": "2026-06-29", "source": "Fidelity Visa", "description": "HOTEL EXAMPLE SPRINGFIELD IL | FOLIO: 123456",
         "amount": -987.65, "file": "a.pdf"},
        {"date": "2026-06-29", "source": "Fidelity Visa", "description": "HOTEL EXAMPLE SPRINGFIELD IL",
         "amount": -987.65, "mcc": "07011", "file": "b.csv"},
    ])
    assert len(sp.dedupe(df)) == 1


def test_card_payment_wordings_dedupe_and_never_count_as_refunds():
    """A costly bug: 'PAYMENT MADE BY ACCOUNT ENDING IN:…' (CSV) wasn't recognised
    as a card payment, so each one was booked as a REFUND that cut spending."""
    df = _frame([
        {"date": "2026-07-16", "source": "Fidelity Visa", "description": "PAYMENT THANK YOU",
         "amount": 1234.50, "file": "a.pdf"},
        {"date": "2026-07-16", "source": "Fidelity Visa",
         "description": "PAYMENT MADE BY ACCOUNT ENDING IN:9999", "amount": 1234.50, "file": "b.csv"},
    ])
    out = sp.dedupe(df)
    assert len(out) == 1
    alone = sr.classify(df.iloc[[1]].reset_index(drop=True), sr.load_rules(None))
    assert alone.iloc[0]["kind"] == "transfer" and alone.iloc[0]["spend"] == 0.0


def test_foreign_purchase_dedupes_across_csv_and_pdf():
    csv_rows = sp.parse_fidelity_csv(
        '"Date","Transaction","Name","Memo","Amount"\n'
        '"2026-04-20","DEBIT","RIDEAPP example CN - 50.0000 CHINA YUAN RENMINBI","1; 04121; ; ; ;","-7.25"\n',
        "b.csv")
    assert csv_rows[0]["description"] == "RIDEAPP example CN | 50.0000 CHINA YUAN RENMINBI"
    df = _frame([{"date": "2026-04-20", "source": "Fidelity Visa",
                  "description": "RIDEAPP example CN | 50.00 CHINA YUAN RENMINBI",
                  "amount": -7.25, "file": "a.pdf"}])
    both = pd.concat([df, pd.DataFrame(csv_rows, columns=sp.COLUMNS)], ignore_index=True)
    both["date"] = pd.to_datetime(both["date"])
    assert len(sp.dedupe(both)) == 1



# ---------------------------------------------------------------- payback attribution

def _pb_rules():
    return sr.load_rules(None)


def test_payback_counts_in_the_month_of_the_bill_it_splits():
    df = _frame([
        {"date": "2026-01-20", "source": "Ally", "description": "CITY WATER BILL | ACH Withdrawal", "amount": -1200.00},
        {"date": "2026-02-04", "source": "Venmo", "description": "Sam Roe — Water bill | Venmo Payment",
         "amount": 600.00, "counterparty": "Sam Roe", "note": "Water bill", "raw_type": "Payment", "ref": "1"},
    ])
    out = sr.classify(df, _pb_rules())
    pb = out[out["kind"] == "payback"].iloc[0]
    assert pb["category"] == "Utilities"
    assert pb["eff_date"] == pd.Timestamp("2026-01-20")        # half of January's bill


def test_one_split_shares_a_category():
    """Four friends each send $75 within a day: 3 say 'Beach trip', one says '🏠'."""
    rows = [{"date": f"2026-06-{d}", "source": "Venmo", "description": f"F{i} — {n} | Venmo Payment",
             "amount": 75.0, "counterparty": f"F{i}", "note": n, "raw_type": "Payment", "ref": str(i)}
            for i, (d, n) in enumerate([("28", "Beach trip"), ("28", "Beach trip 🏐"), ("29", "Beach trip"), ("29", "🏠")])]
    out = sr.classify(_frame(rows), _pb_rules())
    assert set(out["category"]) == {"Travel"}


def test_vague_note_needs_a_near_exact_split_of_a_shareable_purchase():
    df = _frame([
        {"date": "2026-05-01", "source": "Card", "description": "AUTO INSURANCE CO", "mcc": "06300", "amount": -150.00},
        {"date": "2026-05-02", "source": "Card", "description": "NOODLE HOUSE", "mcc": "05812", "amount": -70.00},
        {"date": "2026-05-03", "source": "Venmo", "description": "A — 💥 | Venmo Payment", "amount": 50.00,
         "counterparty": "A", "note": "💥", "raw_type": "Payment", "ref": "1"},   # 1/3 of insurance: coincidence
        {"date": "2026-05-03", "source": "Venmo", "description": "B — 💥 | Venmo Payment", "amount": 35.00,
         "counterparty": "B", "note": "💥", "raw_type": "Payment", "ref": "2"},   # exactly half of dinner
    ])
    out = sr.classify(df, _pb_rules()).set_index("ref")
    assert out.loc["1", "category"] == sr.PAYBACK_FALLBACK                   # never 'Insurance'
    assert out.loc["2", "category"] == "Dining"



def test_current_housing_ignores_refinance_noise():
    """Old payments, a skipped month and a tax bill must not leak into 'now'."""
    rows = []
    for m, amt in [("2025-09", 2500), ("2025-10", 5200), ("2025-11", 0), ("2025-12", 3100),
                   ("2026-01", 3100), ("2026-02", 3100)]:
        if amt:
            rows.append({"date": f"{m}-03", "source": "Ally", "description": "LENDER MORTGAGE | ACH",
                         "amount": -amt})
    tx = sr.classify(_frame(rows), sr.load_rules(None))
    tx["month"] = tx["eff_date"].dt.to_period("M")
    months = list(pd.period_range("2025-09", "2026-02", freq="M"))
    assert sd.current_housing(tx, months) == pytest.approx(3100.0)


def test_refund_counts_in_the_purchase_month():
    df = _frame([
        {"date": "2026-08-10", "source": "Card", "description": "JEWELER CHECKOUT NY", "amount": -2400.00},
        {"date": "2026-09-14", "source": "Card", "description": "JEWELER CHECKOUT NY", "amount": 300.00},
    ])
    out = sr.classify(df, sr.load_rules(None))
    refund = out[out["amount"] > 0].iloc[0]
    assert refund["eff_date"] == pd.Timestamp("2026-08-10") and refund["spend"] == -300.00


def test_travel_payback_reaches_a_trip_booked_months_ahead():
    rows = [{"date": "2026-03-11", "source": "Card", "description": "LODGING SITE", "mcc": "07011", "amount": -400.00}]
    rows += [{"date": "2026-06-28", "source": "Venmo", "description": f"F{i} — Beach trip | Venmo Payment",
              "amount": 80.0, "counterparty": f"F{i}", "note": "Beach trip", "raw_type": "Payment", "ref": str(i)}
             for i in range(4)]
    out = sr.classify(_frame(rows), sr.load_rules(None))
    pb = out[out["kind"] == "payback"]
    assert (pb["eff_date"] == pd.Timestamp("2026-03-11")).all() and (pb["category"] == "Travel").all()


def test_loan_proceeds_are_not_spending_or_a_housing_refund():
    df = _frame([{"date": "2025-10-31", "source": "Ally", "amount": 1500.00,
                  "description": "EXAMPLE LENDER PAYOUT*PROCEEDS | Direct Deposit"}])
    out = sr.classify(df, sr.load_rules(None))
    assert out.iloc[0]["kind"] == "transfer"


def test_rent_payer_small_payments_are_paybacks():
    rules = sr.load_rules(None)
    rules["income_counterparties"] = {"Rae Tenant": {"label": "Rent", "min_amount": 400}}
    rows = [{"date": "2026-07-05", "source": "Venmo", "description": f"Rae Tenant — {n} | Venmo Payment",
             "amount": a, "counterparty": "Rae Tenant", "note": n, "raw_type": "Payment", "ref": str(a)}
            for a, n in ((900.0, "🎫"), (60.0, "⛽"))]
    out = sr.classify(_frame(rows), rules).set_index("ref")
    assert (out.loc["900.0", "kind"], out.loc["900.0", "reason"]) == ("income", "Rent")
    assert out.loc["60.0", "kind"] == "payback" and out.loc["60.0", "category"] == "Auto & transport"


def test_transfer_reason_label():
    rules = sr.load_rules(None)
    rules["transfer_reasons"] = {"Sam Lender": "Loan repayment"}
    df = _frame([{"date": "2025-10-15", "source": "Ally", "amount": -10000.0,
                  "description": "Ally to Ally Transfer ACCT: 1 NAME: Sam Lender | Ally to Ally Transfer"}])
    out = sr.classify(df, rules)
    assert (out.iloc[0]["kind"], out.iloc[0]["reason"]) == ("transfer", "Loan repayment")


def test_pie_averages_every_complete_month_including_housing():
    tx = _dash_tx()
    jul = pd.Period("2026-07", "M")
    avg = sd.group_averages(tx, [jul])
    assert list(avg.index) == sd.GROUPS
    assert avg["Housing"] == pytest.approx(2000.0) and avg.sum() == pytest.approx(2049.0)
    fig = sd.pie_figure(avg, dark=False)
    assert "Utilities" not in fig.data[0].labels          # net negative month: no negative slice
    assert sum(fig.data[0].values) == pytest.approx(2089.0)  # positive slices only


# ---------------------------------------------------------------- bug-hunt regressions

def test_venmo_me_found_even_when_handle_has_a_suffix():
    text = VENMO_CSV.replace("(@Pat-Doe)", "(@Pat-Doe-3)")
    rows = {r["ref"]: r for r in sp.parse_venmo_csv(text, "v.csv")}
    assert rows["1002"]["counterparty"] == "Lee Poe" and rows["1001"]["counterparty"] == "Sam Roe"


def test_bill_autopay_is_spending_card_autopay_is_transfer():
    df = _frame([{"date": "2026-07-01", "source": "Card", "description": "VERIZON WIRELESS AUTOPAY", "amount": -80},
                 {"date": "2026-07-01", "source": "Ally", "description": "AMEX EPAYMENT ACH PMT", "amount": -900}])
    out = sr.classify(df, sr.load_rules(None)).set_index("description")
    assert out.loc["VERIZON WIRELESS AUTOPAY", "kind"] == "spend"
    assert out.loc["AMEX EPAYMENT ACH PMT", "kind"] == "transfer"


def test_merchant_key_ignores_order_ids():
    assert sr.merchant_key("AMAZON MKTPL*AB1CD2EF3 Amzn.com/bill WA") == \
        sr.merchant_key("AMAZON MKTPL*ZZ9YY8XX7 Amzn.com/bill WA")
    assert sr.merchant_key("TST* EXAMPLE BISTRO ANYTOWN") != sr.merchant_key("TST* OTHER PLACE")


@pytest.mark.parametrize("desc,not_cat", [("PHO HOA RESTAURANT", "Housing"), ("TST* GOOD NEIGHBORHOOD CAFE", "Subscriptions"),
                                          ("POKEMON CENTER", "Dining"), ("PETCO PARK", "Pets")])
def test_keyword_false_friends(desc, not_cat):
    assert sr.merchant_category({"description": desc, "mcc": "", "raw_category": ""}, sr.load_rules(None)) != not_cat


def test_split_vote_needs_a_majority():
    rows = [{"date": f"2026-06-0{d}", "source": "Venmo", "description": f"F{i} — {n} | Venmo Payment", "amount": 20.0,
             "counterparty": f"F{i}", "note": n, "raw_type": "Payment", "ref": str(i)}
            for i, (d, n) in enumerate([("1", "dinner"), ("2", "uber"), ("3", "water bill")])]
    out = sr.classify(_frame(rows), sr.load_rules(None)).set_index("ref")
    assert list(out.loc[["0", "1", "2"], "category"]) == ["Dining", "Auto & transport", "Utilities"]


def test_housing_now_adds_separately_paid_costs_since_the_current_payment():
    rows = [{"date": f"{m}-03", "source": "Ally", "description": "LENDER MORTGAGE | ACH", "amount": -a}
            for m, a in [("2025-09", 3000), ("2025-10", 3000), ("2025-11", 4000), ("2025-12", 4000), ("2026-01", 4000)]]
    rows += [{"date": "2025-10-10", "source": "Ally", "description": "COUNTY OF X TAX | ACH", "amount": -6000},   # old regime
             {"date": "2025-12-10", "source": "Ally", "description": "COUNTY OF X TAX | ACH", "amount": -1200}]   # current
    tx = sr.classify(_frame(rows), sr.load_rules(None))
    tx["month"] = tx["eff_date"].dt.to_period("M")
    months = list(pd.period_range("2025-09", "2026-01", freq="M"))
    assert sd.current_housing(tx, months) == pytest.approx(4000.0 + 1200.0 / 3)


def test_venmo_one_payment_month_tie_goes_to_the_handle():
    text = ("Account Statement - (@Pat-Doe-3) ,,,,,,,,,\nAccount Activity,,,,,,,,,\n"
            ",ID,Datetime,Type,Status,Note,From,To,Amount (total),Funding Source,Destination\n"
            ",1,2026-07-05T10:00:00,Payment,Complete,rent,Rae Tenant,Pat Doe,+ $900.00,,Venmo balance\n")
    assert sp.parse_venmo_csv(text, "v.csv")[0]["counterparty"] == "Rae Tenant"



# ---------------------------------------------------------------- filters, moving average, period

def test_filters_limit_counted_rows_only():
    tx = _dash_tx()
    v = sd.apply_filters(tx, ["Food & groceries"])
    counted_groups = set(sd.counted(v)["category"].map(sd.expense_group))
    assert counted_groups == {"Food & groceries"}
    assert (v["kind"] == "transfer").sum() == (tx["kind"] == "transfer").sum()   # Data tab unaffected
    big = sd.apply_filters(tx, None, drop_oneoffs=True)
    assert sd.counted(big)["spend"].abs().max() < sd.ONE_OFF                      # $2,000 mortgage gone


def test_moving_average_skips_incomplete_months():
    months = pd.period_range("2026-01", "2026-04", freq="M")
    series = pd.Series([100.0, 0.0, 300.0, 500.0], index=months)          # Feb is a missing statement
    ma = sd.moving_average(series, [m for m in months if str(m) != "2026-02"], 3)
    assert ma[pd.Period("2026-03", "M")] == pytest.approx(200.0)          # (100 + 300) / 2, not /3
    assert ma[pd.Period("2026-04", "M")] == pytest.approx(400.0)          # Feb skipped


def test_every_headline_number_follows_the_period():
    rows = [{"date": "2026-06-05", "source": "Card", "description": "CAFE ONE", "mcc": "05814", "amount": -100},
            {"date": "2026-07-05", "source": "Card", "description": "CAFE ONE", "mcc": "05814", "amount": -300}]
    tx = sr.classify(_frame(rows), sr.load_rules(None))
    tx["month"] = tx["eff_date"].dt.to_period("M"); tx["merchant"] = tx["description"]
    jun, jul = pd.Period("2026-06", "M"), pd.Period("2026-07", "M")
    both = sd.kpis(tx, jun, jul, [jun, jul])["per_month"]
    only_jul = sd.kpis(tx, jul, jul, [jun, jul])["per_month"]
    assert (both, only_jul) == (200.0, 300.0)
    assert sd.group_averages(tx, [jul])["Food & groceries"] == 300.0


def test_category_table_counts_and_orders():
    t = sd.category_table(_dash_tx(), pd.Period("2026-07", "M"), pd.Period("2026-07", "M"))
    assert t.iloc[0]["Category"] == "Housing"                              # biggest total first
    dining = t.set_index("Category").loc["Dining"]
    assert dining["Transactions"] == 4 and dining["Largest"] == pytest.approx(25.0)


def test_charts_draw_the_chosen_moving_average():
    tx = _dash_tx()
    jul = pd.Period("2026-07", "M")
    t = sd.monthly_table(tx, jul, jul)
    fig = sd.monthly_figure(t, [], False, sd.moving_average(t["Net"], [jul], 3), 3)
    assert "3-month average" in [tr.name for tr in fig.data]
    assert "6-month average" in [tr.name for tr in
                                 sd.category_trend_figure(tx, "Food & groceries", jul, jul, [], False, 6).data]
    assert all("average" not in (tr.name or "") for tr in
               sd.category_trend_figure(tx, "Food & groceries", jul, jul, [], False, 0).data)



# ---------------------------------------------------------------- fixed monthly estimates

def _with_estimate():
    tx = _dash_tx()
    rules = {"fixed_monthly": [{"label": "Partner's spending", "amount": 2000, "category": "Partner spending"}]}
    return sd.add_fixed_items(tx, rules)


def test_fixed_estimate_is_one_line_per_month():
    tx = _with_estimate()
    est = tx[tx["source"] == sd.ESTIMATE_SOURCE]
    assert len(est) == tx["month"].nunique() and (est["spend"] == 2000).all()
    assert set(est["category"].map(sd.expense_group)) == {"Partner spending"}
    jul = pd.Period("2026-07", "M")
    assert sd.kpis(tx, jul, jul, [jul])["per_month"] == pytest.approx(2049.0 + 2000.0)


def test_estimate_survives_hide_one_offs_and_follows_include():
    tx = _with_estimate()
    hidden = sd.apply_filters(tx, None, drop_oneoffs=True)
    assert (hidden["source"] == sd.ESTIMATE_SOURCE).any()                 # $2,000 but not a one-off
    no_partner = sd.apply_filters(tx, [g for g in sd.GROUPS if g != "Partner spending"])
    assert not (no_partner["source"] == sd.ESTIMATE_SOURCE).any()


def test_partner_bucket_compares_to_the_plan_input():
    jul = pd.Period("2026-07", "M")
    a = sd.actual_plan(_with_estimate(), [jul])
    g = sd.plan_vs_actual({"PARTNER_OTHER_MONTHLY": 2000}, a)
    row = g.set_index("Expense category").loc["Partner spending"]
    assert (row["Your plan"], row["Actual"]) == (2000.0, 2000.0)
    # a single household has no partner spending to copy, estimate or not
    assert "PARTNER_OTHER_MONTHLY" not in sd.actual_plan(_with_estimate(), [jul], partner=False)


def test_estimate_is_drawn_hatched():
    tx = _with_estimate()
    jul = pd.Period("2026-07", "M")
    bars = {t.name: t for t in sd.monthly_figure(sd.monthly_table(tx, jul, jul), [], False).data if t.type == "bar"}
    assert bars["Partner spending"].marker.pattern.shape == "/"
    assert bars["Housing"].marker.pattern.shape in ("", None)
