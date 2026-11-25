"""State income-tax tables, tax year 2026: pinned results.

The brackets and standard deductions come from the BiggerPockets Money Income Tax
Projection Calculator (v1.11.2) and the state agencies it cites; see
docs/DATA_SOURCES.md. Every PINS figure below is what that engine returns for a
wage-only return (standard deduction, no children), checked to the cent against RETpy's
tables by tools/tax_crosscheck. The tests need neither Node nor the BPM page.

Rows where RETpy differs from the source on purpose are pinned separately, with the
reason, so a later table edit cannot change them by accident.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import state_tax_data as std_data  # noqa: E402

INF = float("inf")

# (state, status, gross wages, state income tax): BPM engine output, to the cent.
PINS = [
    ("GA", "S", 100_000, 4241.5), ("GA", "MFJ", 200_000, 8483), ("GA", "HOH", 100_000, 4241.5),
    ("NC", "S", 100_000, 3481.27), ("NC", "MFJ", 200_000, 6962.55),
    ("NC", "HOH", 100_000, 3226.91), ("IA", "S", 100_000, 3188.2),
    ("IA", "MFJ", 200_000, 6376.4), ("IA", "HOH", 100_000, 2882.3),
    ("CO", "S", 100_000, 3691.6), ("CO", "MFJ", 200_000, 7383.2),
    ("CO", "HOH", 100_000, 3337.4), ("LA", "S", 100_000, 2613.75),
    ("LA", "MFJ", 200_000, 5227.5), ("LA", "HOH", 100_000, 2613.75),
    ("KY", "S", 100_000, 3382.4), ("KY", "HOH", 100_000, 3382.4),
    ("MD", "S", 100_000, 4538.38), ("MD", "MFJ", 200_000, 9283.25),
    ("MD", "HOH", 100_000, 4379.25), ("MN", "S", 100_000, 5276.61),
    ("MN", "MFJ", 200_000, 10813.05), ("NY", "S", 100_000, 4859.75),
    ("NY", "MFJ", 200_000, 9712.8), ("NY", "HOH", 100_000, 4546.57),
    ("HI", "S", 100_000, 5883.2), ("HI", "MFJ", 200_000, 11766.4),
    ("HI", "HOH", 100_000, 5024.8), ("OR", "S", 100_000, 8176.37),
    ("OR", "MFJ", 200_000, 16352.75), ("MS", "S", 100_000, 3508), ("MS", "MFJ", 200_000, 7416),
    ("MS", "HOH", 100_000, 3464), ("WV", "S", 100_000, 3782.5), ("WV", "MFJ", 200_000, 8362.5),
    ("WV", "HOH", 100_000, 3782.5), ("IN", "S", 100_000, 2950), ("IN", "MFJ", 200_000, 5900),
    ("IN", "HOH", 100_000, 2950), ("NE", "S", 100_000, 3846.46),
    ("NE", "MFJ", 200_000, 7692.91), ("ID", "S", 100_000, 4191.77),
    ("ID", "MFJ", 200_000, 8383.54), ("MT", "S", 100_000, 4289.1),
    ("MT", "MFJ", 200_000, 8578.2), ("MT", "HOH", 100_000, 3834.28),
    ("MA", "S", 100_000, 5000), ("MA", "MFJ", 200_000, 10000), ("MA", "HOH", 100_000, 5000),
    ("NM", "S", 100_000, 3569.1), ("NM", "MFJ", 200_000, 7411.2),
    ("NM", "HOH", 100_000, 2953.95), ("VT", "S", 100_000, 4489.6),
    ("VT", "MFJ", 200_000, 9508.95), ("OH", "S", 100_000, 2365.62),
    ("OH", "MFJ", 200_000, 5115.62), ("OH", "HOH", 100_000, 2365.62),
    ("OK", "S", 100_000, 3999.5), ("OK", "MFJ", 200_000, 7999), ("ME", "S", 100_000, 5507.75),
    ("ME", "MFJ", 200_000, 11014.82), ("ME", "HOH", 100_000, 4769.93),
    ("RI", "S", 100_000, 3397.5), ("RI", "MFJ", 200_000, 7615.5),
    ("RI", "HOH", 100_000, 3131.5), ("MO", "S", 100_000, 3762.67),
    ("MO", "MFJ", 200_000, 7705.97), ("MO", "HOH", 100_000, 3384.32),
    ("ND", "S", 100_000, 690.79), ("ND", "MFJ", 200_000, 1693.09),
    ("VA", "S", 100_000, 4989.38), ("VA", "MFJ", 200_000, 10236.25),
    ("VA", "HOH", 100_000, 4989.38),
]


def _state_tax(code, status, gross):
    """Bracket tax on ``gross`` less the state's standard deduction alone (no personal
    exemption: BPM does not model them)."""
    row = std_data.STATES[code]
    deduction = row["std_deduction"]
    deduction = (cfg.STANDARD_DEDUCTION_BY_STATUS[status] if deduction == "federal"
                 else deduction[status])
    return cfg.progressive_tax(row["brackets"][status], max(0.0, gross - deduction))


@pytest.mark.parametrize("code,status,gross,expected", PINS)
def test_state_tax_matches_the_bpm_engine_to_the_cent(code, status, gross, expected):
    # Within a cent: the BPM figures are rounded to cents, and some sit on a half-cent.
    assert _state_tax(code, status, gross) == pytest.approx(expected, abs=0.006)


class TestTablesAre2026:
    def test_every_row_and_the_constant_say_2026(self):
        assert std_data.TAX_YEAR == 2026
        assert {row["year"] for row in std_data.STATES.values()} == {2026}

    def test_top_rates_that_changed(self):
        top = {c: std_data.STATES[c]["brackets"]["S"][-1][1] for c in std_data.STATES}
        assert top["IA"] == .038 and top["LA"] == .03 and top["GA"] == .0499
        assert top["NC"] == .0399 and top["KY"] == .035 and top["MS"] == .04
        assert top["CO"] == .044 and top["MD"] == .065 and top["ME"] == .0915
        assert top["AR"] == .037 and top["UT"] == .0445 and top["SC"] == .0521
        assert top["ID"] == .053 and top["WV"] == .0458 and top["IN"] == .0295

    def test_georgia_deduction_and_working_year_tax(self):
        assert std_data.STATES["GA"]["std_deduction"] == {"S": 15_000, "MFJ": 30_000,
                                                          "HOH": 15_000}
        t = cfg.working_year_taxes(200_000, status="MFJ", partner=True, state="GA",
                                   children_under_17=0)
        assert t["state"] == pytest.approx(8_483.00, abs=0.005)      # BPM: 4.99% x 170,000

    def test_north_carolina_single_through_the_working_year_path(self):
        t = cfg.working_year_taxes(100_000, status="S", partner=False, state="NC",
                                   children_under_17=0)
        assert t["state"] == pytest.approx(3_481.27, abs=0.005)

    def test_california_is_untouched(self):
        ca = std_data.STATES["CA"]
        assert ca["year"] == 2026
        assert ca["brackets"]["S"][0] == (11_456, .01)
        assert ca["brackets"]["MFJ"][-1] == (INF, .123)
        assert ca["std_deduction"] == {"S": 5_900, "MFJ": 11_800, "HOH": 11_800}
        assert ca["exemption_credits"]["personal"] == 158
        assert ca["surtax"] == {"threshold": 1_000_000, "rate": 0.01}
        assert ca["payroll"] == {"rate": 0.013, "wage_cap": None}


class TestAppOnlyFieldsSurvive:
    def test_rules_bpm_does_not_model_are_kept(self):
        s = std_data.STATES
        assert s["PA"]["pretax_401k_taxed"] is True
        assert s["NJ"]["hsa_taxed"] is True and s["CA"]["hsa_taxed"] is True
        assert s["MT"]["social_security"] == "taxed" and s["UT"]["social_security"] == "taxed"
        assert s["MN"]["social_security"] == {"exempt_below_agi": {
            "S": 82_190, "MFJ": 105_380, "HOH": 82_190}}
        assert s["GA"]["retirement_exclusion"] == [{"min_age": 62, "per_person": 35_000},
                                                   {"min_age": 65, "per_person": 65_000}]
        assert s["ND"]["ltcg_exclusion"] == 0.40 and s["SC"]["ltcg_exclusion"] == 0.44
        assert s["IL"]["exemption"] == 2_775 and s["MI"]["exemption"] == 5_600
        assert s["AL"]["std_deduction"] == {"S": 2_500, "MFJ": 5_000, "HOH": 2_500}

    def test_confidence_labels_follow_the_approximations(self):
        s = std_data.STATES
        assert s["AR"]["confidence"] == "approx" and s["SC"]["confidence"] == "approx"
        assert s["OH"]["confidence"] == "medium" and s["UT"]["confidence"] == "medium"


class TestDeliberateDifferencesFromBpm:
    def test_arizona_keeps_the_federal_deduction(self):
        """BPM lists 8,350 / 16,700, which matches no federal or Arizona figure."""
        assert std_data.STATES["AZ"]["std_deduction"] == "federal"
        assert cfg.state_tax_rules("AZ", "S")["deduction"] == cfg.STANDARD_DEDUCTION_SINGLE

    def test_kentucky_joint_return_gets_two_deductions(self):
        """BPM gives a joint return one $3,360; Kentucky gives each taxpayer one."""
        assert std_data.STATES["KY"]["std_deduction"] == {"S": 3_360, "MFJ": 6_720,
                                                          "HOH": 3_360}
        assert _state_tax("KY", "MFJ", 200_000) == pytest.approx(6_764.80)   # BPM: 6,882.40

    def test_louisiana_exemption_is_gone_with_the_new_deduction(self):
        row = std_data.STATES["LA"]
        assert row["exemption"] == 0 and row["std_deduction"]["S"] == 12_875

    def test_head_of_household_keeps_its_own_schedule_where_bpm_copies_single(self):
        """BPM lists Single's figures for head of household in these states."""
        assert std_data.STATES["MN"]["std_deduction"]["HOH"] == 21_900
        assert std_data.STATES["VT"]["std_deduction"]["HOH"] == 11_100
        assert std_data.STATES["OK"]["std_deduction"]["HOH"] == 9_350
        assert std_data.STATES["OR"]["std_deduction"]["HOH"] == 4_420
        assert std_data.STATES["NE"]["std_deduction"]["HOH"] == 12_150
        assert std_data.STATES["ID"]["brackets"]["HOH"] == std_data.STATES["ID"]["brackets"]["MFJ"]
        assert std_data.STATES["MN"]["brackets"]["HOH"][0] == (39_010, .0535)

    def test_federal_head_of_household_24_percent_top_is_the_statute_figure(self):
        """BPM tops the HoH 24% band at 201,775; Rev. Proc. 2025-32 says 201,750."""
        hoh = cfg.FEDERAL_BRACKETS_BY_STATUS["HOH"]
        assert (201_750, .24) in hoh and (256_200, .32) in hoh


class TestApproximatedMechanics:
    """Rows whose 2026 mechanics are not plain brackets: one bracket set, documented."""

    def test_ohio_is_exact_above_26050(self):
        # ORC 5747.02 (as BPM models it): 0 up to 26,050, then 332 + 2.75% of the excess.
        brackets = std_data.STATES["OH"]["brackets"]["S"]
        for taxable in (26_051, 36_050, 100_000, 500_000):
            assert cfg.progressive_tax(brackets, taxable) == pytest.approx(
                332 + .0275 * (taxable - 26_050), abs=0.03)
        # Below that the smoothed rate overstates by up to the 332 base amount.
        assert cfg.progressive_tax(brackets, 26_050) == pytest.approx(332)
        assert cfg.progressive_tax(brackets, 13_000) == 0

    def test_arkansas_uses_the_graduated_table_only(self):
        assert std_data.STATES["AR"]["brackets"]["S"] == [
            (5_599, 0.0), (11_199, .02), (15_999, .03), (26_399, .034), (INF, .037)]
        # BPM adds about $290 above 94,700 of taxable income (second table): not modeled.
        assert cfg.progressive_tax(std_data.STATES["AR"]["brackets"]["S"],
                                   100_000) == pytest.approx(3_332.84, abs=0.01)

    def test_utah_flat_rate_without_the_taxpayer_credit(self):
        assert std_data.STATES["UT"]["brackets"]["S"] == [(INF, .0445)]
        assert std_data.STATES["UT"]["std_deduction"] == {"S": 0, "MFJ": 0, "HOH": 0}

    def test_south_carolina_two_rates_and_full_sciad(self):
        assert std_data.STATES["SC"]["brackets"]["MFJ"] == [(30_000, .0199), (INF, .0521)]
        assert std_data.STATES["SC"]["std_deduction"] == {"S": 15_000, "MFJ": 30_000,
                                                          "HOH": 22_500}
