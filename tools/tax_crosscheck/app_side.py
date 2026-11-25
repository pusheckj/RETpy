"""RETpy side of the tax cross-check: ONE fixture in a fresh Python process.

Usage: python3 app_side.py '<fixture json>'     (prints one JSON object on stdout)

Never import this from the driver. It sets config values (filing status, state, ages)
on the shared ``retirement_sim.config`` module, so each fixture gets its own process
and the global state dies with it. The driver (crosscheck.py) never imports
retirement_sim at all.

Two engine paths are used, as in the app:
  * mix "W2": ``config.working_year_taxes`` (the working-year source of truth);
  * retirement mixes: ``AccountPortfolio`` marginal tax, taxable-account gains
    (``_tax_home_sale_gain`` = the same pieces as a taxable-account sale) and
    ``_true_up_social_security_tax``, booked in the order the engine books them
    (ordinary income, gains, then Social Security). Each is booked as the change in one
    whole-year figure, so the booked federal tax is the year's tax in IRS order.
Each fixture runs twice: "modeled" (the app as shipped) and "neutral" (state rules BPM
does not model switched off: personal exemptions and credits, retirement exclusions,
the capital-gains exclusion, taxed Social Security except in Utah, which BPM also taxes).
"""
import json
import os
import sys

os.environ["RETIREMENT_SIM_PROFILE"] = "/nonexistent/tax-crosscheck-profile.json"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from retirement_sim import account_simulation as asim  # noqa: E402
from retirement_sim import config as cfg  # noqa: E402
from retirement_sim import state_tax_data  # noqa: E402

_ORIG_RULES = cfg.state_tax_rules
RULES = ("exemption", "retirement_exclusion", "ltcg_exclusion", "social_security", "credits")


def _patch_rules(neutralize):
    """Make ``cfg.state_tax_rules`` return rules with the named app-only rules off."""
    def patched(*args, **kwargs):
        rules = _ORIG_RULES(*args, **kwargs)
        row = state_tax_data.STATES.get(rules["code"])
        if not row:
            return rules
        if "exemption" in neutralize:
            std = row["std_deduction"]
            std = (cfg.STANDARD_DEDUCTION_BY_STATUS[rules["status"]]
                   if std == "federal" else std[rules["status"]])
            rules["deduction"] = float(std)
        if "retirement_exclusion" in neutralize:
            rules["retirement_exclusion"] = None
        if "ltcg_exclusion" in neutralize:
            rules["ltcg_exclusion"] = 0.0
        if "social_security" in neutralize and rules["code"] != "UT":
            # BPM exempts Social Security in every state but Utah, where it taxes the
            # federally taxable part like RETpy does.
            rules["social_security"] = "exempt"
        if "credits" in neutralize:
            rules["exemption_credits"] = None
        return rules
    cfg.state_tax_rules = patched


def _configure(fx):
    cfg.CURRENT_YEAR = 2026                      # senior deduction window 2025-2028
    cfg.FILING_STATUS = fx["status"]
    cfg.YOUR_AGE = fx["age"]
    cfg.PARTNER_AGE = fx["age"] if fx["status"] == "MFJ" else 0
    cfg.STATE_CHOICE = fx["state"]
    cfg.RETIREMENT_STATE_CHOICE = None
    cfg.INCLUDE_SOCIAL_SECURITY = True
    cfg.CHILDREN = []


def _ages(fx):
    return [fx["age"], fx["age"]] if fx["status"] == "MFJ" else [fx["age"]]


def _w2(fx):
    t = cfg.working_year_taxes(
        fx["wages"], 0.0, your_age=fx["age"],
        partner_age=fx["age"] if fx["status"] == "MFJ" else None,
        status=fx["status"], partner=(fx["status"] == "MFJ"), state=fx["state"],
        children_under_17=0)
    return {"fed_ordinary": t["federal"], "ltcg_tax": 0.0, "niit": 0.0,
            "state_tax": t["state"] - t["state_payroll"], "sdi": t["state_payroll"],
            "fica": t["fica"], "agi": fx["wages"], "ss_taxable": 0.0}


def _engine(fx):
    status = fx["status"]
    p = asim.AccountPortfolio()
    p.update_ages(fx["age"])
    p.reset_yearly_income()
    ordinary, gains, ss = fx.get("ordinary", 0.0), fx.get("ltcg", 0.0), fx.get("ss", 0.0)
    booked_federal = 0.0              # federal income tax booked event by event (no NIIT)

    def book(event):
        """Run one engine booking call; add its federal income tax to the running total."""
        nonlocal booked_federal
        state0, niit0 = p.total_state_taxes_paid, p.total_niit_paid
        tax = event()
        booked_federal += (tax - (p.total_state_taxes_paid - state0)
                           - (p.total_niit_paid - niit0))

    if ordinary > 0:
        book(lambda: p.calculate_marginal_tax_on_income(
            ordinary, owner="you", retirement=fx.get("retirement", True)))
    if gains > 0:
        book(lambda: p._tax_home_sale_gain(gains))
    ss_taxable = 0.0
    if ss > 0:
        ss_taxable = cfg.calculate_taxable_social_security(
            ss, p._return_income("you") + p._return_investment("you"), 0, status)
        book(lambda: asim._true_up_social_security_tax(p, ss, 0.0))
    # The engine books every event as the change in one whole-year figure, so the booked
    # total is the year's federal income tax. Ordinary tax comes from the final year's
    # taxable ordinary income; what is left of the booked total is the gains tax.
    magi = p.year_ordinary_income + p.year_investment_income
    ordinary_taxable = max(0.0, p.year_ordinary_income - p.get_standard_deduction("you", magi))
    fed_ordinary = p._federal_model("you").calculate_tax(ordinary_taxable)
    return {"fed_ordinary": fed_ordinary, "ltcg_tax": booked_federal - fed_ordinary,
            "niit": p.total_niit_paid,
            "state_tax": p.total_state_taxes_paid, "sdi": 0.0,
            "fica": 0.0, "agi": magi, "ss_taxable": ss_taxable}


def _irs(fx, ordinary, gains, taxable_ss):
    """The same return computed straight from the app's tables, in IRS order (all income
    known at once): deduction at the return's MAGI, gains stacked on ordinary taxable
    income, NIIT on the final MAGI. Isolates table errors from engine sequencing."""
    status = fx["status"]
    agi = ordinary + taxable_ss + gains
    std = cfg.standard_deduction_for_return(status, _ages(fx), agi, 0.0)
    taxable = max(0.0, agi - std)
    ordinary_taxable = max(0.0, taxable - gains)
    return {"fed_ordinary": cfg.progressive_tax(cfg.get_federal_brackets(status),
                                                ordinary_taxable),
            "ltcg_tax": asim.calculate_ltcg_tax(taxable - ordinary_taxable, ordinary_taxable,
                                                status=status),
            "niit": cfg.calculate_niit(agi, gains, 0.0, status)}


def _run(fx):
    out = _w2(fx) if fx["mix"] == "W2" else _engine(fx)
    if fx["mix"] != "W2":
        out["irs"] = _irs(fx, fx.get("ordinary", 0.0), fx.get("ltcg", 0.0), out["ss_taxable"])
    magi = out["agi"]
    out["irmaa_tier"] = cfg.medicare_irmaa_tier(magi, status=fx["status"])
    # 65+ add-on plus the OBBBA senior deduction, at this return's MAGI (BPM has no
    # field for them: the driver passes the sum in "other OBBBA deductions").
    out["std_extra"] = (cfg.standard_deduction_for_return(fx["status"], _ages(fx), magi, 0.0)
                        - cfg.STANDARD_DEDUCTION_BY_STATUS[fx["status"]])
    return out


def _bpm_parts(fx):
    """BPM's default example: feed BPM's own intermediate figures to RETpy's tables."""
    b = fx["bpm_result"]
    status, kids = fx["status"], fx["children"]
    ordinary_taxable = b["income"]["ordinaryTaxable"]
    prefs = b["income"]["preferential"]
    fed = cfg.progressive_tax(cfg.get_federal_brackets(status), ordinary_taxable)
    ltcg = asim.calculate_ltcg_tax(prefs, ordinary_taxable, status=status)
    rules = cfg.state_tax_rules(fx["state"], status, people=2)
    state = cfg.progressive_tax(rules["brackets"], b["state"]["stateTaxable"])
    ctc = cfg.child_tax_credit(kids, fed + ltcg, b["income"]["agi"], fx["earned_income"],
                               status)
    t = cfg.working_year_taxes(100_000, 67_000, your_age=45, partner_age=45, status=status,
                               partner=True, state=fx["state"], children_under_17=0)
    return {"fed_ordinary": fed, "ltcg_tax": ltcg, "state_tax": state, "ctc": ctc,
            "fica": t["fica"]}


def main():
    fx = json.loads(sys.argv[1])
    _configure(fx)
    if fx["mix"] == "BPM_PARTS":
        print(json.dumps(_bpm_parts(fx)))
        return
    result = {"id": fx["id"], "modeled": _run(fx)}
    _patch_rules(set(RULES))
    result["neutral"] = _run(fx)
    # Which app-only rules moved the result? (only when modeled != neutral)
    contrib = []
    if abs(result["modeled"]["state_tax"] - result["neutral"]["state_tax"]) > 0.005:
        for rule in RULES:
            _patch_rules({rule})
            if abs(_run(fx)["state_tax"] - result["modeled"]["state_tax"]) > 0.005:
                contrib.append(rule)
    result["contrib"] = contrib
    print(json.dumps(result))


if __name__ == "__main__":
    main()
