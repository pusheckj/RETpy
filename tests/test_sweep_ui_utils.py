"""Function-level coverage for ``ui/utils`` helpers that had NO direct test
(function-gap sweep, 2026-08-22).

Modules covered here: ``coerce``, ``formatting``, ``validation``, ``overrides``,
``plot_theme``, ``profile_io`` (round-trips), ``config_builder``
(``_synthesize_comp_table``), ``derived.get_limit`` and ``mortality``.

``utils`` lives under ``ui/``; add both roots to sys.path (same bootstrap the
other UI-seam tests use).
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UI = os.path.join(_ROOT, "ui")
for _p in (_ROOT, _UI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import math

import pytest

from retirement_sim import config as cfg
from utils import coerce, config_builder, derived, formatting, mortality, plot_theme, profile_io
from utils import overrides as ov
from utils.validation import validate_run_inputs


class FakeSt:
    """Minimal Streamlit stand-in: only ``session_state`` is used by these utils."""

    def __init__(self, **state):
        self.session_state = dict(state)


# ---------------------------------------------------------------------------
# coerce
# ---------------------------------------------------------------------------
class TestSafeInt:
    @pytest.mark.parametrize("value,expected", [
        (5, 5), (0, 0), (-3, -3), (5.9, 5), (-5.9, -5), ("42", 42), (True, 1),
    ])
    def test_happy_path(self, value, expected):
        assert coerce.safe_int(value) == expected

    @pytest.mark.parametrize("value", [None, "", "abc", [], {}, object()])
    def test_bad_values_use_default(self, value):
        assert coerce.safe_int(value) == 0
        assert coerce.safe_int(value, 7) == 7

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_uses_default(self, value):
        assert coerce.safe_int(value, -1) == -1

    def test_very_large(self):
        assert coerce.safe_int(10 ** 20) == 10 ** 20

    def test_default_is_coerced_to_int(self):
        assert coerce.safe_int(None, 3.7) == 3

    # FIXED 2026-08-22: was xfail(strict) while the defect stood; the fix is in.
    @pytest.mark.parametrize("value,expected", [("12.7", 12), ("-12.7", -12), ("1e3", 1000)])
    def test_decimal_strings_should_truncate_not_vanish(self, value, expected):
        assert coerce.safe_int(value) == expected


class TestSafeFloat:
    @pytest.mark.parametrize("value,expected", [
        (5, 5.0), (0, 0.0), (-2.5, -2.5), ("12.7", 12.7), ("1e3", 1000.0),
    ])
    def test_happy_path(self, value, expected):
        assert coerce.safe_float(value) == pytest.approx(expected)

    @pytest.mark.parametrize("value", [None, "", "abc", [], float("nan"), float("inf")])
    def test_bad_values_use_default(self, value):
        assert coerce.safe_float(value) == 0.0
        assert coerce.safe_float(value, 1.5) == 1.5

    def test_result_is_always_finite(self):
        for v in (float("nan"), float("-inf"), "nan_but_not_a_number"):
            assert math.isfinite(coerce.safe_float(v))


class TestAsFraction:
    @pytest.mark.parametrize("value,expected", [
        (0.04, 0.04), (4.0, 0.04), (100, 1.0), (0.0, 0.0), (1.5, 1.5), (1.51, 0.0151),
    ])
    def test_dual_form_threshold(self, value, expected):
        assert coerce.as_fraction(value) == pytest.approx(expected)

    def test_none_uses_default_without_rescaling(self):
        assert coerce.as_fraction(None, 0.03) == pytest.approx(0.03)

    def test_default_above_threshold_is_still_rescaled(self):
        # The default flows through the same >1.5 rule.
        assert coerce.as_fraction(None, 5.0) == pytest.approx(0.05)

    def test_idempotent_for_fractional_input(self):
        for v in (0.0, 0.01, 0.07, 1.0):
            assert coerce.as_fraction(coerce.as_fraction(v)) == pytest.approx(coerce.as_fraction(v))

    def test_negative_is_passed_through(self):
        assert coerce.as_fraction(-0.02) == pytest.approx(-0.02)


class TestEnsureDefault:
    def test_seeds_only_when_absent(self):
        st = FakeSt()
        assert coerce.ensure_default(st, "k", 5) == 5
        assert st.session_state["k"] == 5
        # Second call must NOT overwrite a user/sync-supplied value.
        st.session_state["k"] = 9
        assert coerce.ensure_default(st, "k", 5) == 9
        assert st.session_state["k"] == 9

    def test_falsy_existing_value_is_preserved(self):
        st = FakeSt(k=0)
        assert coerce.ensure_default(st, "k", 5) == 0

    def test_broken_st_returns_default(self):
        class NoState:
            pass
        assert coerce.ensure_default(NoState(), "k", 42) == 42


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------
class TestMoney:
    @pytest.mark.parametrize("value,expected", [
        (0, "$0"), (1, "$1"), (1234567, "$1,234,567"),
        (-1000, "-$1,000"), (-0.4, "-$0"), (999, "$999"),
    ])
    def test_plain(self, value, expected):
        assert formatting.money(value) == expected

    @pytest.mark.parametrize("value", [None, float("nan"), float("inf"), float("-inf")])
    def test_bad_values_render_em_dash(self, value):
        assert formatting.money(value) == "—"
        assert formatting.pct(value) == "—"
        assert formatting.age(value) == "—"
        assert formatting.years(value) == "—"
        assert formatting.basis_points(value) == "—"
        assert formatting.signed_pct(value) == "—"

    @pytest.mark.parametrize("value,expected", [
        (999, "$999"), (1_000, "$1.0K"), (1_500, "$1.5K"),
        (1_000_000, "$1.0M"), (1_234_567, "$1.2M"),
        (1_000_000_000, "$1.0B"), (-2_500_000, "-$2.5M"),
    ])
    def test_shorten_boundaries(self, value, expected):
        assert formatting.money(value, shorten=True) == expected

    def test_precision(self):
        assert formatting.money(1234.567, precision=2) == "$1,234.57"
        assert formatting.money(1_234_567, precision=0, shorten=True) == "$1.2M"

    def test_money_md_escapes_dollar_for_latex_safety(self):
        assert formatting.money_md(1000) == "\\$1,000"
        assert formatting.money_md(-1000) == "-\\$1,000"
        assert "$" not in formatting.money_md(None)
        # Two amounts in one caption must not leave an unescaped $...$ pair.
        caption = f"{formatting.money_md(10)} to {formatting.money_md(20)}"
        assert caption.count("$") == caption.count("\\$")


class TestOtherFormatters:
    @pytest.mark.parametrize("value,expected", [
        (0.82, "82.0%"), (0.0, "0.0%"), (1.0, "100.0%"), (-0.05, "-5.0%"),
    ])
    def test_pct(self, value, expected):
        assert formatting.pct(value) == expected

    def test_pct_precision(self):
        assert formatting.pct(0.8234, precision=2) == "82.34%"
        assert formatting.pct(0.8234, precision=0) == "82%"

    @pytest.mark.parametrize("value,expected", [
        (42, "Age 42"), (42.4, "Age 42"), (42.6, "Age 43"), (0, "Age 0"),
    ])
    def test_age(self, value, expected):
        assert formatting.age(value) == expected

    @pytest.mark.parametrize("value,expected", [
        (1, "1 year"), (0, "0 years"), (2, "2 years"), (1.4, "1 year"),
        (0.6, "1 year"), (1.5, "2 years"),
        # Only exactly +1 is singular; a negative count keeps the plural "s".
        (-1, "-1 years"),
    ])
    def test_years_pluralization(self, value, expected):
        assert formatting.years(value) == expected

    @pytest.mark.parametrize("value,expected", [
        (0.0015, "15 bps"), (0.0, "0 bps"), (0.01, "100 bps"), (0.00004, "0 bps"),
    ])
    def test_basis_points(self, value, expected):
        assert formatting.basis_points(value) == expected

    @pytest.mark.parametrize("value,expected", [
        (0.05, "+5.0%"), (-0.05, "-5.0%"), (0.0, "+0.0%"),
    ])
    def test_signed_pct(self, value, expected):
        assert formatting.signed_pct(value) == expected

    def test_signed_pct_never_shows_double_sign(self):
        assert formatting.signed_pct(-0.123) == "-12.3%"
        assert "--" not in formatting.signed_pct(-0.123)


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
class TestValidateRunInputs:
    def test_valid_age_targeted_run(self):
        assert validate_run_inputs({"YOUR_AGE": 30, "PLAN_UNTIL_AGE": 90}, 45) == []

    def test_retire_at_current_age_is_allowed(self):
        assert validate_run_inputs({"YOUR_AGE": 30, "PLAN_UNTIL_AGE": 90}, 30) == []

    def test_target_below_current_age_errors(self):
        errs = validate_run_inputs({"YOUR_AGE": 40, "PLAN_UNTIL_AGE": 90}, 30)
        assert len(errs) == 1 and "below your current age" in errs[0]

    def test_plan_until_equal_to_target_errors(self):
        errs = validate_run_inputs({"YOUR_AGE": 30, "PLAN_UNTIL_AGE": 45}, 45)
        assert len(errs) == 1 and "must be after" in errs[0]

    def test_both_problems_reported_together(self):
        errs = validate_run_inputs({"YOUR_AGE": 50, "PLAN_UNTIL_AGE": 40}, 45)
        assert len(errs) == 2

    def test_none_target_only_checks_horizon(self):
        assert validate_run_inputs({"YOUR_AGE": 30, "PLAN_UNTIL_AGE": 31}, None) == []
        errs = validate_run_inputs({"YOUR_AGE": 30, "PLAN_UNTIL_AGE": 30}, None)
        assert len(errs) == 1 and "after your current age" in errs[0]

    def test_string_ages_are_accepted(self):
        assert validate_run_inputs({"YOUR_AGE": "30", "PLAN_UNTIL_AGE": "90"}, "45") == []

    def test_unparseable_ages_skip_validation_instead_of_crashing(self):
        assert validate_run_inputs({"YOUR_AGE": None, "PLAN_UNTIL_AGE": 90}, 45) == []
        assert validate_run_inputs({"YOUR_AGE": "old"}, 45) == []

    def test_missing_keys_fall_back_to_config(self):
        assert validate_run_inputs({}, cfg.YOUR_AGE + 5) == []

    def test_empty_overrides_and_no_target_is_ok(self):
        assert validate_run_inputs({}, None) == []


# ---------------------------------------------------------------------------
# overrides (session-state accessors)
# ---------------------------------------------------------------------------
class TestOverrideAccessors:
    def test_get_on_empty_state(self):
        st = FakeSt()
        assert ov.get_override(st, "X") is None
        assert ov.get_override(st, "X", 5) == 5

    def test_set_creates_the_container(self):
        st = FakeSt()
        ov.set_override(st, "X", 7)
        assert st.session_state["user_overrides"] == {"X": 7}
        assert ov.get_override(st, "X") == 7

    def test_set_preserves_existing_entries(self):
        st = FakeSt(user_overrides={"A": 1})
        ov.set_override(st, "B", 2)
        assert st.session_state["user_overrides"] == {"A": 1, "B": 2}

    def test_round_trip_preserves_falsy_values(self):
        st = FakeSt()
        for value in (0, False, "", None):
            ov.set_override(st, "K", value)
            assert ov.get_override(st, "K", "SENTINEL") == value


# ---------------------------------------------------------------------------
# plot_theme
# ---------------------------------------------------------------------------
class TestPlotTheme:
    def test_all_palettes_are_valid_hex_and_distinct(self):
        for name, pal in plot_theme.PALETTES.items():
            assert len(pal) >= 10, name
            assert len(set(pal)) == len(pal), name
            for c in pal:
                assert c.startswith("#") and len(c) == 7, (name, c)
                int(c[1:], 16)

    def test_active_palette_defaults(self):
        assert plot_theme.active_palette(None) == plot_theme.PALETTES["Pastel"]
        assert plot_theme.active_palette(FakeSt()) == plot_theme.PALETTES["Pastel"]

    def test_active_palette_follows_choice(self):
        st = FakeSt(palette_choice="Vibrant")
        assert plot_theme.active_palette(st) == plot_theme.PALETTES["Vibrant"]

    def test_unknown_palette_choice_falls_back(self):
        st = FakeSt(palette_choice="Neon Disaster")
        assert plot_theme.active_palette(st) == plot_theme.PALETTES["Pastel"]

    def test_broken_st_falls_back(self):
        class Broken:
            @property
            def session_state(self):
                raise RuntimeError("no context")
        assert plot_theme.active_palette(Broken()) == plot_theme.PALETTES["Pastel"]
        assert plot_theme.is_dark(Broken()) is False

    def test_series_color_cycles(self):
        pal = plot_theme.PALETTES["Pastel"]
        assert plot_theme.series_color(0) == pal[0]
        assert plot_theme.series_color(len(pal)) == pal[0]
        assert plot_theme.series_color(len(pal) + 3) == pal[3]

    def test_assign_colors_is_order_stable_and_covers_every_name(self):
        names = ["a", "b", "c"]
        mapping = plot_theme.assign_colors(names)
        assert list(mapping) == names
        assert mapping == plot_theme.assign_colors(names)
        pal = plot_theme.PALETTES["Pastel"]
        assert list(mapping.values()) == pal[:3]

    def test_assign_colors_empty_and_long(self):
        assert plot_theme.assign_colors([]) == {}
        many = [f"n{i}" for i in range(40)]
        mapping = plot_theme.assign_colors(many)
        assert len(mapping) == 40

    @pytest.mark.parametrize("mode,expected", [
        ("Dark", True), ("🌙 Dark", True), ("Light", False), ("", False), (None, False),
    ])
    def test_is_dark(self, mode, expected):
        assert plot_theme.is_dark(FakeSt(theme_mode=mode)) is expected

    def test_is_dark_missing_key(self):
        assert plot_theme.is_dark(FakeSt()) is False

    def test_style_fig_themes_both_modes(self):
        import plotly.graph_objects as go
        for mode, expected_paper in (("Light", "rgba(0,0,0,0)"), ("Dark", "rgba(0,0,0,0)")):
            fig = go.Figure(go.Scatter(x=[1, 2], y=[3, 4]))
            out = plot_theme.style_fig(fig, FakeSt(theme_mode=mode))
            assert out is fig  # mutates and returns the same object
            assert fig.layout.font.color is not None
        light = plot_theme.style_fig(go.Figure(go.Scatter(x=[1], y=[1])), FakeSt(theme_mode="Light"))
        dark = plot_theme.style_fig(go.Figure(go.Scatter(x=[1], y=[1])), FakeSt(theme_mode="Dark"))
        assert light.layout.font.color != dark.layout.font.color

    def test_style_fig_is_idempotent(self):
        import plotly.graph_objects as go
        st = FakeSt(theme_mode="Dark")
        fig = plot_theme.style_fig(go.Figure(go.Scatter(x=[1], y=[1])), st)
        once = fig.to_plotly_json()["layout"]
        fig = plot_theme.style_fig(fig, st)
        assert fig.to_plotly_json()["layout"] == once


class TestBeeswarm:
    def test_empty(self):
        assert plot_theme.beeswarm_xy([], 3) == ([], [])
        assert plot_theme.beeswarm_xy([None, None], 3) == ([], [])

    def test_lengths_match_and_values_preserved(self):
        values = [1, 5, 5, 5, 9, 2, None, 7]
        xs, ys = plot_theme.beeswarm_xy(values, 10)
        assert len(xs) == len(ys) == 7
        assert sorted(ys) == sorted(float(v) for v in values if v is not None)

    def test_all_identical_collapses_to_one_column(self):
        xs, ys = plot_theme.beeswarm_xy([4, 4, 4], 2.5)
        assert xs == [2.5, 2.5, 2.5]
        assert ys == [4.0, 4.0, 4.0]

    def test_single_value(self):
        xs, ys = plot_theme.beeswarm_xy([7], 1)
        assert xs == [1.0] and ys == [7.0]

    def test_stays_inside_half_width(self):
        import random
        random.seed(7)
        values = [random.gauss(50, 10) for _ in range(400)]
        for hw in (0.1, 0.42, 1.0):
            xs, _ = plot_theme.beeswarm_xy(values, 30, half_width=hw)
            assert max(abs(x - 30) for x in xs) <= hw + 1e-9

    def test_centered_on_x_center(self):
        values = [1, 2, 2, 3, 3, 3]
        xs, _ = plot_theme.beeswarm_xy(values, 12, n_bins=3)
        assert sum(xs) / len(xs) == pytest.approx(12.0)


# ---------------------------------------------------------------------------
# profile_io round-trips
# ---------------------------------------------------------------------------
class TestProfileRoundTrip:
    def test_simple_round_trip(self):
        data = {"YOUR_AGE": 30, "TARGET_RETIREMENT_AGE": 50,
                "YOUR_401K_MATCH_PCT": 0.04, "LTC_ENABLED": True,
                "STATE_CHOICE": "CA", "NOTHING": None}
        assert profile_io.deserialize_overrides(profile_io.serialize_overrides(data)) == data

    def test_int_keyed_nested_dict_round_trips(self):
        data = {"YOUR_COMPENSATION_BY_AGE": {30: {"base": 100_000, "saved": 5_000},
                                             31: {"base": 103_000, "saved": 6_000}}}
        out = profile_io.deserialize_overrides(profile_io.serialize_overrides(data))
        assert out == data
        assert all(isinstance(k, int) for k in out["YOUR_COMPENSATION_BY_AGE"])

    def test_negative_int_keys_round_trip(self):
        data = {"D": {-3: 1, 0: 2, 7: 3}}
        assert profile_io.deserialize_overrides(profile_io.serialize_overrides(data)) == data

    def test_nested_dict_string_keys_stay_strings(self):
        data = {"SPENDING_GUARDRAILS": {"floor_trigger": 0.70, "floor_reduction": 0.15}}
        assert profile_io.deserialize_overrides(profile_io.serialize_overrides(data)) == data

    def test_tuples_degrade_to_lists(self):
        out = profile_io.deserialize_overrides(profile_io.serialize_overrides({"T": (1, 2)}))
        assert out == {"T": [1, 2]}

    def test_double_round_trip_is_stable(self):
        data = {"A": 1, "B": {5: [1, 2, {"c": 3}]}}
        once = profile_io.deserialize_overrides(profile_io.serialize_overrides(data))
        twice = profile_io.deserialize_overrides(profile_io.serialize_overrides(once))
        assert once == twice == {"A": 1, "B": {5: [1, 2, {"c": 3}]}}

    def test_envelope_metadata_present(self):
        import json
        payload = json.loads(profile_io.serialize_overrides({"A": 1}))
        assert payload["version"] == profile_io.SCHEMA_VERSION
        assert payload["app"] == profile_io.APP_TAG
        assert "saved_at" in payload
        assert payload["overrides"] == {"A": 1}

    def test_empty_dict(self):
        assert profile_io.deserialize_overrides(profile_io.serialize_overrides({})) == {}

    def test_serialize_rejects_non_dict(self):
        for bad in ([1, 2], "x", None, 5):
            with pytest.raises(TypeError):
                profile_io.serialize_overrides(bad)

    def test_bare_legacy_dict_is_accepted(self):
        assert profile_io.deserialize_overrides('{"YOUR_AGE": 31}') == {"YOUR_AGE": 31}

    def test_bytes_input_accepted(self):
        raw = profile_io.serialize_overrides({"A": 2}).encode()
        assert profile_io.deserialize_overrides(raw) == {"A": 2}

    @pytest.mark.parametrize("bad", ["", "{", "not json", "[1,2]", '"str"'])
    def test_malformed_json_raises_valueerror(self, bad):
        with pytest.raises(ValueError):
            profile_io.deserialize_overrides(bad)

    def test_wrong_type_raises_valueerror(self):
        with pytest.raises(ValueError):
            profile_io.deserialize_overrides(None)

    def test_incompatible_major_version_rejected(self):
        payload = '{"version": "2.0", "app": "x", "overrides": {"A": 1}}'
        with pytest.raises(ValueError, match="Incompatible profile schema"):
            profile_io.deserialize_overrides(payload)

    def test_same_major_minor_bump_accepted(self):
        payload = '{"version": "1.7", "app": "x", "overrides": {"A": 1}}'
        assert profile_io.deserialize_overrides(payload) == {"A": 1}

    def test_envelope_with_bad_overrides_type_rejected(self):
        with pytest.raises(ValueError, match="must be an object"):
            profile_io.deserialize_overrides('{"version": "1.0", "overrides": [1,2]}')


# ---------------------------------------------------------------------------
# config_builder._synthesize_comp_table
# ---------------------------------------------------------------------------
class TestSynthesizeCompTable:
    def test_shape_and_keys(self):
        table = config_builder._synthesize_comp_table(100_000, 30, 15, 0.02)
        assert sorted(table) == list(range(30, 45))
        assert all(isinstance(k, int) for k in table)
        for row in table.values():
            # No after_tax: take-home is computed from the tax rules.
            assert set(row) == {"base", "bonus", "rsu_gross", "total_comp", "saved"}

    def test_first_row_is_the_starting_salary(self):
        table = config_builder._synthesize_comp_table(123_456, 40, 3, 0.03)
        assert table[40]["base"] == 123_456
        assert table[40]["total_comp"] == 123_456

    def test_growth_compounds(self):
        table = config_builder._synthesize_comp_table(100_000, 30, 5, 0.10)
        assert table[31]["base"] == 110_000
        assert table[34]["base"] == int(100_000 * 1.10 ** 4)
        bases = [table[a]["base"] for a in sorted(table)]
        assert bases == sorted(bases)

    def test_saved_ratio(self):
        table = config_builder._synthesize_comp_table(100_000, 30, 1, 0.0)
        row = table[30]
        assert row["saved"] == int(100_000 * config_builder.QUICK_INCOME_SAVINGS_RATE)
        assert row["saved"] < row["total_comp"]

    def test_zero_salary_and_zero_rows(self):
        table = config_builder._synthesize_comp_table(0, 30, 2, 0.02)
        assert all(r["base"] == 0 and r["saved"] == 0 for r in table.values())
        assert config_builder._synthesize_comp_table(100_000, 30, 0, 0.02) == {}

    def test_zero_growth_is_flat(self):
        table = config_builder._synthesize_comp_table(80_000, 25, 6, 0.0)
        assert {r["base"] for r in table.values()} == {80_000}

    def test_is_consumable_by_the_engines_savings_helper(self, monkeypatch):
        table = config_builder._synthesize_comp_table(90_000, 35, 10, 0.02)
        monkeypatch.setattr(cfg, "YOUR_COMPENSATION_BY_AGE", table)
        assert cfg.calculate_your_total_savings(35) > 0
        assert cfg.calculate_your_total_savings(60) > 0  # beyond the table


class TestQuickIncomeSplit:
    def test_primary_plus_partner_equals_household_income(self):
        for income in (0, 1, 99_999, 150_000, 1_000_001):
            out = config_builder.build_config_overrides({"HOUSEHOLD_INCOME_QUICK": income,
                                                         "YOUR_AGE": 30})
            primary = out["YOUR_COMPENSATION_BY_AGE"][30]["base"]
            assert primary + out["PARTNER_SALARY"] == income

    def test_ui_only_keys_never_reach_config(self):
        out = config_builder.build_config_overrides(
            {"HOUSEHOLD_INCOME_QUICK": 100_000, "TOTAL_SAVINGS_QUICK": 50_000,
             "TARGET_RETIREMENT_AGE": 55, "NEW_HOME_DOWN_PCT": 0.2,
             "NEW_MORTGAGE_RATE": 0.06, "NEW_HOME_ESCROW_PCT": 0.0135})
        assert not (set(out) & config_builder._UI_ONLY_KEYS)

    def test_total_savings_allocation_sums_to_the_total(self):
        total = 500_000
        out = config_builder.build_config_overrides({"TOTAL_SAVINGS_QUICK": total})
        allocated = sum(out[k] for k in config_builder._DEFAULT_SAVINGS_ALLOCATION)
        # int() truncation loses at most $1 per bucket.
        assert total - len(config_builder._DEFAULT_SAVINGS_ALLOCATION) <= allocated <= total

    def test_allocation_weights_sum_to_one(self):
        assert sum(config_builder._DEFAULT_SAVINGS_ALLOCATION.values()) == pytest.approx(1.0)

    def test_negative_quick_values_are_floored_at_zero(self):
        out = config_builder.build_config_overrides({"HOUSEHOLD_INCOME_QUICK": -50_000,
                                                     "TOTAL_SAVINGS_QUICK": -1, "YOUR_AGE": 30})
        assert out["PARTNER_SALARY"] == 0
        assert out["YOUR_COMPENSATION_BY_AGE"][30]["base"] == 0
        assert all(out[k] == 0 for k in config_builder._DEFAULT_SAVINGS_ALLOCATION)

    def test_explicit_account_balances_suppress_the_quick_allocation(self):
        out = config_builder.build_config_overrides(
            {"TOTAL_SAVINGS_QUICK": 500_000, "YOUR_401K": 12_345})
        assert out["YOUR_401K"] == 12_345
        assert "PARTNER_401K" not in out

    def test_explicit_comp_table_suppresses_synthesis(self):
        table = {30: {"base": 1, "bonus": 0, "rsu_gross": 0,
                      "total_comp": 1, "after_tax": 1, "saved": 0}}
        out = config_builder.build_config_overrides(
            {"HOUSEHOLD_INCOME_QUICK": 200_000, "YOUR_COMPENSATION_BY_AGE": table})
        assert out["YOUR_COMPENSATION_BY_AGE"] == table


# ---------------------------------------------------------------------------
# derived.get_limit
# ---------------------------------------------------------------------------
class TestDerivedGetLimit:
    def test_unknown_name_is_zero(self):
        assert derived.get_limit("nope") == 0
        assert derived.get_limit("") == 0

    def test_401k_catchup_boundary(self):
        assert derived.get_limit("401k", 49) == derived.LIMITS_2024["401k_employee"]
        assert (derived.get_limit("401k", 50)
                == derived.LIMITS_2024["401k_employee"] + derived.LIMITS_2024["401k_catchup_50"])

    def test_ira_catchup_boundary(self):
        assert derived.get_limit("ira", 49) == derived.LIMITS_2024["ira"]
        assert (derived.get_limit("ira", 50)
                == derived.LIMITS_2024["ira"] + derived.LIMITS_2024["ira_catchup_50"])

    def test_hsa_family_flag(self):
        assert derived.get_limit("hsa", 30, family=True) == derived.LIMITS_2024["hsa_family"]
        assert derived.get_limit("hsa", 30, family=False) == derived.LIMITS_2024["hsa_individual"]

    def test_401k_and_ira_agree_with_the_engine(self):
        for age in (30, 49, 50, 60):
            assert derived.get_limit("401k", age) == cfg.get_401k_limit(age, 2024)
            assert derived.get_limit("ira", age) == cfg.get_ira_limit(age, 2024)

    # FIXED 2026-08-22: was xfail(strict) while the defect stood; the fix is in.
    def test_hsa_catchup_at_55_matches_engine(self):
        assert derived.get_limit("hsa", 55, family=True) == cfg.get_hsa_limit(55, 2024, True)


# ---------------------------------------------------------------------------
# mortality
# ---------------------------------------------------------------------------
class TestHazardRatio:
    def test_defaults_are_neutral(self):
        assert mortality.hazard_ratio({}) == pytest.approx(1.0)
        defaults = {k: v["default"] for k, v in mortality.RISK_FACTORS.items()}
        assert mortality.hazard_ratio(defaults) == pytest.approx(1.0)

    def test_every_factor_has_a_neutral_default(self):
        for key, spec in mortality.RISK_FACTORS.items():
            assert spec["default"] in spec["options"], key
            assert spec["options"][spec["default"]] == 1.0, key

    def test_unknown_option_is_treated_as_neutral(self):
        assert mortality.hazard_ratio({"smoking": "Vaping?"}) == pytest.approx(1.0)

    def test_factors_multiply(self):
        rr = mortality.hazard_ratio({"smoking": "Current", "health": "Poor"})
        assert rr == pytest.approx(2.2 * 1.8)

    def test_conditions_multiply_and_unknown_ignored(self):
        assert mortality.hazard_ratio({}, ["Diabetes"]) == pytest.approx(1.5)
        assert mortality.hazard_ratio({}, ["Diabetes", "Heart disease"]) == pytest.approx(1.5 * 1.7)
        assert mortality.hazard_ratio({}, ["Hangnail"]) == pytest.approx(1.0)
        assert mortality.hazard_ratio({}, []) == pytest.approx(1.0)
        assert mortality.hazard_ratio({}, None) == pytest.approx(1.0)

    def test_protective_factors_go_below_one(self):
        rr = mortality.hazard_ratio({"activity": "Active", "health": "Excellent"})
        assert rr < 1.0

    def test_adjusted_mode_is_clamped(self):
        assert mortality._adjusted_mode("Male", 1e12) == 45.0
        assert mortality._adjusted_mode("Male", 1e-12) == 105.0
        assert mortality._adjusted_mode("Male", 0.0) == 105.0  # log(0) guarded
        assert mortality._adjusted_mode("Nonbinary", 1.0) == mortality._BASE_MODE["Male"]


class TestLifeDistribution:
    def test_distribution_invariants(self):
        d = mortality.life_distribution(40, "Male", {})
        assert d["ages"][0] == 40 and d["ages"][-1] == mortality._MAX_AGE
        assert len(d["ages"]) == len(d["death_pdf"]) == len(d["survival"])
        assert sum(d["death_pdf"]) == pytest.approx(1.0)
        assert all(0.0 <= p <= 1.0 for p in d["death_pdf"])
        assert d["survival"][0] == 1.0
        assert all(b <= a + 1e-12 for a, b in zip(d["survival"], d["survival"][1:]))
        assert d["p10"] <= d["median"] <= d["p90"]
        assert d["ages"][0] <= d["mean"] <= d["ages"][-1]

    def test_female_outlives_male_all_else_equal(self):
        m = mortality.life_distribution(40, "Male", {})
        f = mortality.life_distribution(40, "Female", {})
        assert f["median"] > m["median"]
        assert f["mean"] > m["mean"]

    def test_baseline_matches_documented_ssa_calibration(self):
        """Docstring claims life expectancy at 65 ~= 18 (M) / 21 (F)."""
        m = mortality.life_distribution(65, "Male", {})["mean"] - 65
        f = mortality.life_distribution(65, "Female", {})["mean"] - 65
        assert m == pytest.approx(18.0, abs=1.5)
        assert f == pytest.approx(20.5, abs=1.5)

    def test_risk_factors_shorten_life(self):
        healthy = mortality.life_distribution(50, "Male", {"activity": "Active",
                                                           "health": "Excellent"})
        neutral = mortality.life_distribution(50, "Male", {})
        risky = mortality.life_distribution(50, "Male", {"smoking": "Current",
                                                         "health": "Poor"},
                                            ["Diabetes", "COPD / lung disease"])
        assert healthy["mean"] > neutral["mean"] > risky["mean"]
        assert risky["hazard_ratio"] > 1.0 > healthy["hazard_ratio"]

    def test_hazard_shift_matches_the_gompertz_identity(self):
        """RR is a pure horizontal shift of the modal age: M' = M - b*ln(RR)."""
        import math as _m
        d = mortality.life_distribution(40, "Male", {"smoking": "Current"})
        expected = mortality._BASE_MODE["Male"] - mortality._DISPERSION * _m.log(2.2)
        assert d["mode"] == pytest.approx(expected)

    def test_reach_probabilities_are_monotone_and_bounded(self):
        d = mortality.life_distribution(40, "Male", {})
        keys = sorted(d["reach"])
        vals = [d["reach"][k] for k in keys]
        assert all(0.0 <= v <= 1.0 for v in vals)
        assert vals == sorted(vals, reverse=True)

    def test_reach_of_a_past_age_is_certain(self):
        d = mortality.life_distribution(90, "Male", {})
        assert d["reach"][80] == 1.0 and d["reach"][85] == 1.0
        assert d["reach"][95] < 1.0

    @pytest.mark.parametrize("age", [-10, 0, 1, 65, 118, 119, 120, 500])
    def test_extreme_current_ages_are_clamped(self, age):
        d = mortality.life_distribution(age, "Male", {})
        assert 0 <= d["current_age"] <= mortality._MAX_AGE - 1
        assert sum(d["death_pdf"]) == pytest.approx(1.0)
        assert d["median"] >= d["current_age"]

    def test_median_never_precedes_current_age_even_at_extreme_risk(self):
        d = mortality.life_distribution(100, "Male", {"smoking": "Current",
                                                      "health": "Poor",
                                                      "weight": "Severely obese"},
                                        list(mortality.CONDITIONS))
        assert d["median"] >= 100
        assert d["mode"] == 45.0  # clamped

    def test_reach_fn_matches_survival_series(self):
        d = mortality.life_distribution(55, "Female", {})
        for a, s in zip(d["ages"], d["survival"]):
            assert d["reach_fn"][a] == s
