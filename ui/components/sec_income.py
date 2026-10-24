"""Section 2: Income — sources by partner + growth rates + comp table."""
from __future__ import annotations

import pandas as pd

try:
    from utils.coerce import safe_int, safe_float, ensure_default
    from utils.formatting import money
except ImportError:  # pragma: no cover
    from ui.utils.coerce import safe_int, safe_float, ensure_default  # type: ignore
    from ui.utils.formatting import money  # type: ignore

try:
    from utils.overrides import get_override, set_override
    from utils.config_builder import QUICK_INCOME_SAVINGS_RATE as _SAVED_SHARE
except ImportError:  # pragma: no cover
    from ui.utils.overrides import get_override, set_override  # type: ignore
    from ui.utils.config_builder import QUICK_INCOME_SAVINGS_RATE as _SAVED_SHARE  # type: ignore

_OTHER_INCOME_HELP = ("Taxable income that isn't pay, such as rent, interest or side "
                      "work. Counted while working; no Social Security/Medicare tax.")


def _income_input(st, label: str, widget_key: str, override_key: str,
                  default: int, max_value: int = 2_000_000, step: int = 1_000,
                  help_text: str = "") -> int:
    ensure_default(st, widget_key, safe_int(get_override(st, override_key, default), default))
    v = st.number_input(
        f"{label} ($)", min_value=0, max_value=max_value, step=step,
        key=widget_key, help=help_text or None,
    )
    set_override(st, override_key, safe_int(v))
    return safe_int(v)


def _build_comp_table(start_age, target_age, base, bonus, rsu, growth):
    end_age = max(start_age + 9, target_age)
    rows = []
    for offset in range(end_age - start_age + 1):
        age = start_age + offset
        scale = (1 + growth) ** offset
        rows.append({
            "age": age,
            "base": int(round(base * scale)),
            "bonus": int(round(bonus * scale)),
            "rsu_gross": int(round(rsu * scale)),
        })
    return pd.DataFrame(rows)


def render_body(st) -> None:
    overrides = st.session_state.get("user_overrides", {}) or {}
    has_partner = safe_int(overrides.get("PARTNER_AGE", 0), 0) > 0

    # ----- You -----
    st.markdown("**You**")
    c1, c2 = st.columns(2)
    with c1:
        you_base = _income_input(st, "💼 Base salary", "si_your_base",
                                 "YOUR_BASE_SALARY", 70_000)
        you_bonus = _income_input(st, "🎁 Bonus", "si_your_bonus",
                                  "YOUR_BONUS_AMOUNT", 0, max_value=1_000_000, step=500)
    with c2:
        you_rsu = _income_input(st, "📈 RSU (gross, annual)", "si_your_rsu",
                                "YOUR_RSU_AMOUNT", 0, max_value=5_000_000)
        you_other = _income_input(st, "🔄 Other income", "si_your_other",
                                  "YOUR_OTHER_INCOME", 0, max_value=1_000_000, step=500,
                                  help_text=_OTHER_INCOME_HELP)

    ensure_default(st, "si_your_growth",
                   safe_float(get_override(st, "YOUR_SALARY_GROWTH_RATE", 0.02), 0.02) * 100)
    r = st.slider("Your salary growth rate (%/yr, real)", min_value=0.0,
                  max_value=10.0, step=0.5, key="si_your_growth")
    set_override(st, "YOUR_SALARY_GROWTH_RATE", r / 100)
    you_growth = r / 100

    you_total = you_base + you_bonus + you_rsu + you_other

    # ----- Partner -----
    if has_partner:
        st.markdown("**Partner**")
        c3, c4 = st.columns(2)
        with c3:
            p_base = _income_input(st, "💼 Partner base salary", "si_partner_base",
                                   "PARTNER_BASE_SALARY", 42_000)
            p_bonus = _income_input(st, "🎁 Partner bonus", "si_partner_bonus",
                                    "PARTNER_BONUS_AMOUNT", 0, max_value=1_000_000, step=500)
        with c4:
            p_rsu = _income_input(st, "📈 Partner RSU (gross)", "si_partner_rsu",
                                  "PARTNER_RSU_AMOUNT", 0, max_value=5_000_000)
            p_other = _income_input(st, "🔄 Partner other income", "si_partner_other",
                                    "PARTNER_OTHER_INCOME", 0, max_value=1_000_000, step=500,
                                    help_text=_OTHER_INCOME_HELP)

        ensure_default(st, "si_partner_growth",
                       safe_float(get_override(st, "PARTNER_SALARY_GROWTH_RATE", 0.02), 0.02) * 100)
        r = st.slider("Partner salary growth rate (%/yr, real)", min_value=0.0,
                      max_value=10.0, step=0.5, key="si_partner_growth")
        set_override(st, "PARTNER_SALARY_GROWTH_RATE", r / 100)

        p_total = p_base + p_bonus + p_rsu + p_other
        # The engine reads PARTNER_SALARY as base pay and adds the partner's
        # bonus, RSU and other income itself.
        set_override(st, "PARTNER_SALARY", safe_int(p_base))
    else:
        st.caption("Single household — no partner income.")
        # Zero out partner fields
        for k in ("PARTNER_BASE_SALARY", "PARTNER_BONUS_AMOUNT", "PARTNER_RSU_AMOUNT",
                  "PARTNER_OTHER_INCOME", "PARTNER_SALARY"):
            set_override(st, k, 0)
        p_total = 0

    household_total = you_total + p_total
    set_override(st, "HOUSEHOLD_INCOME_QUICK", safe_int(household_total))

    # KPI strip
    # NOTE: do NOT inject metric CSS here. An earlier unscoped
    # `[data-testid="stMetricValue"] { overflow: visible; white-space: nowrap }`
    # block leaked app-wide, defeated Streamlit's own ellipsis clipping, and made
    # the 32px sidebar metric values overlap each other into unreadable mush.
    # Sidebar metric sizing now lives in styles/theme.css (sidebar-scoped).
    st.markdown(
        '<hr style="margin: 12px 0 8px 0; border: 0; border-top: 1px solid #e5e7eb;">',
        unsafe_allow_html=True,
    )
    cols = st.columns(3, gap="small")
    with cols[0]: st.metric("You", money(you_total, shorten=True))
    with cols[1]: st.metric("Partner", money(p_total, shorten=True))
    with cols[2]: st.metric("Household", money(household_total, shorten=True))

    # Comp table editor (advanced)
    with st.expander("Edit compensation table", expanded=False):
        st.caption("Year-by-year base/bonus/RSU, auto-derived from your inputs above. "
                   "Edit any cell to customize a year, or click 🔄 to resync.")

        if "si_comp_customized" not in st.session_state:
            st.session_state["si_comp_customized"] = False
        customized = bool(st.session_state["si_comp_customized"])

        # The button gets its OWN full-width row. It used to sit in the 1/4
        # column of st.columns([3, 1]), which in the 328px sidebar is 47px wide —
        # the label wrapped to one character per line and the button rendered as
        # a 47x347px vertical stack of letters.
        if customized:
            st.caption("✏️ Customized — manual edits preserved.")
        else:
            st.caption("🔄 Auto-derived from base/bonus/RSU + growth rate above.")

        if st.button("🔄 Sync to inputs", key="si_comp_sync", width="stretch"):
            if "si_comp_editor" in st.session_state:
                try: del st.session_state["si_comp_editor"]
                except Exception: pass
            fresh = _build_comp_table(
                safe_int(get_override(st, "YOUR_AGE", 30), 30),
                safe_int(get_override(st, "TARGET_RETIREMENT_AGE", 60), 60),
                you_base, you_bonus, you_rsu, you_growth,
            )
            new_table = {}
            for _, row in fresh.iterrows():
                age = safe_int(row["age"])
                base = safe_int(row["base"])
                bonus = safe_int(row["bonus"])
                rsu = safe_int(row["rsu_gross"])
                total = base + bonus + rsu
                new_table[age] = {
                    "base": base, "bonus": bonus, "rsu_gross": rsu,
                    "total_comp": total, "saved": int(total * _SAVED_SHARE),
                }
            set_override(st, "YOUR_COMPENSATION_BY_AGE", new_table)
            st.session_state["si_comp_customized"] = False
            st.rerun()

        # Build df from existing or auto-derive
        existing = get_override(st, "YOUR_COMPENSATION_BY_AGE", None)
        if customized and existing:
            df = pd.DataFrame([
                {"age": age, "base": safe_int(d.get("base", 0)),
                 "bonus": safe_int(d.get("bonus", 0)), "rsu_gross": safe_int(d.get("rsu_gross", 0))}
                for age, d in sorted(existing.items())
            ])
        else:
            df = _build_comp_table(
                safe_int(get_override(st, "YOUR_AGE", 30), 30),
                safe_int(get_override(st, "TARGET_RETIREMENT_AGE", 60), 60),
                you_base, you_bonus, you_rsu, you_growth,
            )

        edited = st.data_editor(
            df, num_rows="dynamic", width="stretch", key="si_comp_editor",
            column_config={
                "age": st.column_config.NumberColumn("Age", min_value=18, max_value=80, step=1),
                "base": st.column_config.NumberColumn("Base", min_value=0, step=1_000, format="$%d"),
                "bonus": st.column_config.NumberColumn("Bonus", min_value=0, step=500, format="$%d"),
                "rsu_gross": st.column_config.NumberColumn("RSU", min_value=0, step=1_000, format="$%d"),
            },
        )

        # Detect customization
        if not customized:
            try:
                derived = _build_comp_table(
                    safe_int(get_override(st, "YOUR_AGE", 30), 30),
                    safe_int(get_override(st, "TARGET_RETIREMENT_AGE", 60), 60),
                    you_base, you_bonus, you_rsu, you_growth,
                )
                if not edited.reset_index(drop=True).equals(derived.reset_index(drop=True)):
                    st.session_state["si_comp_customized"] = True
            except Exception:
                pass

        # Persist back to overrides
        new_table = {}
        for _, row in edited.iterrows():
            age = safe_int(row["age"])
            base = safe_int(row.get("base", 0))
            bonus = safe_int(row.get("bonus", 0))
            rsu = safe_int(row.get("rsu_gross", 0))
            total = base + bonus + rsu
            # No after_tax: the simulation computes take-home from the tax
            # rules (the Taxes section shows the same figure).
            new_table[age] = {
                "base": base, "bonus": bonus, "rsu_gross": rsu,
                "total_comp": total, "saved": int(total * _SAVED_SHARE),
            }
        set_override(st, "YOUR_COMPENSATION_BY_AGE", new_table)


def render(st) -> None:
    with st.expander("Income", expanded=False, icon=":material/payments:"):
        render_body(st)
