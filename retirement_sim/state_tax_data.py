"""
State income tax tables: all 50 states + DC, tax year 2024.

License: MIT (see LICENSE at project root)

Plain data only. ``config.state_tax_rules`` turns a row into the parameters of
one state return and ``config.working_year_taxes`` / the engine's
``StateIncomeTax`` apply them. Like the federal tables, the figures are held
flat in today's dollars for the whole plan.

Row fields
----------
name              display name
year              tax year the figures come from
confidence        "high"   -- brackets, deduction and the rules below are complete
                              to within rounding for a typical household
                  "medium" -- rates and brackets are right, but a credit,
                              phase-out or local tax is left out (usually well
                              under 1% of income); see ``note``
                  "approx" -- simplified or uncertain figures; the UI labels the
                              state as approximate. Verify with
                              docs/state_tax_research_prompt.md.
brackets          {"S"|"MFJ"|"HOH": [(upper_limit, rate), ...]}, last limit inf.
                  Taxable income = state income - deduction.
std_deduction     {"S"|"MFJ"|"HOH": dollars}, or "federal" (the federal standard
                  deduction for the filing status, without the 65+ add-on)
exemption         personal exemption deducted from income: dollars per person
                  (2 people on a joint return), or {"S"|"MFJ"|"HOH": dollars}
social_security   "exempt" | "taxed" (the federally taxable part) |
                  {"exempt_below_agi": {"S"|"MFJ"|"HOH": dollars}} -- exempt when
                  the return's income is below the limit, taxed above (a cliff;
                  real phase-outs are gentler)
retirement_exclusion
                  None, or a list of {"min_age", "per_person"} tiers: up to
                  ``per_person`` a year of each person's traditional 401(k)/IRA
                  distributions is state-tax-free once they reach ``min_age``
                  (the highest tier they qualify for applies). Roth conversions
                  never qualify here.
ltcg_exclusion    share of long-term capital gains the state does not tax
pretax_401k_taxed True where 401(k) deferrals are still state wages (PA)
hsa_taxed         True where HSA payroll contributions are still state wages
payroll           employee state payroll tax on wages: {"rate", "wage_cap"}
note              what is simplified, local taxes left out, known changes

Not modeled anywhere: credits (child, earned-income, personal-exemption
credits), dependent exemptions, itemized deductions, alternative minimum
taxes, city/county income taxes, and bracket "recapture" for top earners.
"""

INF = float("inf")

TAX_YEAR = 2024


def _same(brackets):
    return {"S": brackets, "MFJ": brackets, "HOH": brackets}


def _flat(rate, zero_up_to=None):
    if zero_up_to is None:
        return _same([(INF, rate)])
    return {k: [(v, 0.0), (INF, rate)] for k, v in zero_up_to.items()}


_NONE = _same([(INF, 0.0)])


def _no_tax(name, note=""):
    return dict(name=name, year=TAX_YEAR, confidence="high", brackets=_NONE,
                std_deduction={"S": 0, "MFJ": 0, "HOH": 0}, exemption=0,
                social_security="exempt", retirement_exclusion=None,
                note=note or "No state income tax on wages or retirement income.")


STATES = {
    "AL": dict(
        name="Alabama", year=2024, confidence="approx",
        brackets={"S": [(500, .02), (3_000, .04), (INF, .05)],
                  "MFJ": [(1_000, .02), (6_000, .04), (INF, .05)],
                  "HOH": [(500, .02), (3_000, .04), (INF, .05)]},
        # Income-tested standard deduction: the floor that applies above ~$35k.
        std_deduction={"S": 2_500, "MFJ": 5_000, "HOH": 2_500},
        exemption={"S": 1_500, "MFJ": 3_000, "HOH": 3_000},
        social_security="exempt",
        retirement_exclusion=[{"min_age": 65, "per_person": 6_000}],
        note="Alabama lets you deduct federal income tax paid; that is not "
             "modeled, so this overstates Alabama tax. Defined-benefit pensions "
             "are fully exempt (only the $6,000 exclusion at 65+ is modeled for "
             "401(k)/IRA money). Some cities add an occupational tax."),
    "AK": _no_tax("Alaska"),
    "AZ": dict(
        name="Arizona", year=2024, confidence="high",
        brackets=_flat(.025), std_deduction="federal", exemption=0,
        social_security="exempt", retirement_exclusion=None,
        note="Flat 2.5%."),
    "AR": dict(
        name="Arkansas", year=2024, confidence="approx",
        brackets=_flat(.039), std_deduction={"S": 2_340, "MFJ": 4_680, "HOH": 2_340},
        exemption=0, social_security="exempt",
        retirement_exclusion=[{"min_age": 59.5, "per_person": 6_000}],
        ltcg_exclusion=0.50,
        note="Approximated as the 3.9% top rate on all taxable income (the lower "
             "brackets and the $29 personal credit are left out), so lower "
             "incomes are slightly overstated."),
    "CA": dict(
        name="California", year=2024, confidence="high",
        brackets={
            "S": [(10_756, .01), (25_499, .02), (40_245, .04), (55_866, .06),
                  (70_606, .08), (360_659, .093), (432_787, .103),
                  (721_314, .113), (1_000_000, .123), (INF, .133)],
            "MFJ": [(21_512, .01), (50_998, .02), (80_490, .04), (111_732, .06),
                    (141_212, .08), (721_318, .093), (865_574, .103),
                    (1_000_000, .113), (1_442_628, .123), (INF, .133)],
            "HOH": [(21_527, .01), (51_000, .02), (65_744, .04), (81_364, .06),
                    (96_107, .08), (490_493, .093), (588_593, .103),
                    (980_987, .113), (1_000_000, .123), (INF, .133)],
        },
        std_deduction={"S": 5_540, "MFJ": 11_080, "HOH": 11_080},
        exemption=0, social_security="exempt", retirement_exclusion=None,
        hsa_taxed=True, payroll={"rate": 0.011, "wage_cap": None},
        note="Includes the 1% mental-health surtax above $1M and State "
             "Disability Insurance (1.1% of all wages in 2024). Personal "
             "exemption credits ($149 per person) are left out."),
    "CO": dict(
        name="Colorado", year=2024, confidence="medium",
        brackets=_flat(.0425), std_deduction="federal", exemption=0,
        social_security="exempt",
        retirement_exclusion=[{"min_age": 55, "per_person": 20_000},
                              {"min_age": 65, "per_person": 24_000}],
        note="4.25% is the 2024 rate after the TABOR refund trigger; the "
             "standing rate is 4.40%. Social Security is fully deductible at 65+ "
             "and partly at 55-64 (treated as exempt)."),
    "CT": dict(
        name="Connecticut", year=2024, confidence="medium",
        brackets={
            "S": [(10_000, .02), (50_000, .045), (100_000, .055), (200_000, .06),
                  (250_000, .065), (500_000, .069), (INF, .0699)],
            "MFJ": [(20_000, .02), (100_000, .045), (200_000, .055), (400_000, .06),
                    (500_000, .065), (1_000_000, .069), (INF, .0699)],
            "HOH": [(16_000, .02), (80_000, .045), (160_000, .055), (320_000, .06),
                    (400_000, .065), (800_000, .069), (INF, .0699)],
        },
        std_deduction={"S": 0, "MFJ": 0, "HOH": 0}, exemption=0,
        social_security="exempt", retirement_exclusion=None,
        note="The personal exemption (gone by ~$44k single / $71k joint) and "
             "the high-income recapture of the low brackets are left out. Up to "
             "25% of Social Security is taxed above $75k/$100k income (treated "
             "as exempt). Pension/IRA exclusions for lower incomes are not "
             "modeled."),
    "DE": dict(
        name="Delaware", year=2024, confidence="medium",
        brackets=_same([(2_000, 0.0), (5_000, .022), (10_000, .039), (20_000, .048),
                        (25_000, .052), (60_000, .0555), (INF, .066)]),
        std_deduction={"S": 3_250, "MFJ": 6_500, "HOH": 3_250}, exemption=0,
        social_security="exempt",
        retirement_exclusion=[{"min_age": 60, "per_person": 12_500}],
        note="The $110 personal credit is left out. Wilmington's 1.25% city "
             "wage tax is not included."),
    "DC": dict(
        name="District of Columbia", year=2024, confidence="high",
        brackets=_same([(10_000, .04), (40_000, .06), (60_000, .065), (250_000, .085),
                        (500_000, .0925), (1_000_000, .0975), (INF, .1075)]),
        std_deduction="federal", exemption=0,
        social_security="exempt", retirement_exclusion=None,
        note=""),
    "FL": _no_tax("Florida"),
    "GA": dict(
        name="Georgia", year=2024, confidence="medium",
        brackets=_flat(.0539), std_deduction={"S": 12_000, "MFJ": 24_000, "HOH": 12_000},
        exemption=0, social_security="exempt",
        retirement_exclusion=[{"min_age": 62, "per_person": 35_000},
                              {"min_age": 65, "per_person": 65_000}],
        note="Flat 5.39% for 2024 (scheduled to keep falling). Dependent "
             "exemptions are left out."),
    "HI": dict(
        name="Hawaii", year=2024, confidence="approx",
        brackets={
            "S": [(2_400, .014), (4_800, .032), (9_600, .055), (14_400, .064),
                  (19_200, .068), (24_000, .072), (36_000, .076), (48_000, .079),
                  (150_000, .0825), (175_000, .09), (200_000, .10), (INF, .11)],
            "MFJ": [(4_800, .014), (9_600, .032), (19_200, .055), (28_800, .064),
                    (38_400, .068), (48_000, .072), (72_000, .076), (96_000, .079),
                    (300_000, .0825), (350_000, .09), (400_000, .10), (INF, .11)],
            "HOH": [(3_600, .014), (7_200, .032), (14_400, .055), (21_600, .064),
                    (28_800, .068), (36_000, .072), (54_000, .076), (72_000, .079),
                    (225_000, .0825), (262_500, .09), (300_000, .10), (INF, .11)],
        },
        std_deduction={"S": 4_400, "MFJ": 8_800, "HOH": 6_424}, exemption=1_144,
        social_security="exempt", retirement_exclusion=None,
        note="Hawaii's 2024 law (Act 46) raises the standard deduction and widens "
             "the brackets in stages from 2024; the figures here may lag it. "
             "Employer-funded pensions are exempt but 401(k)/IRA money is taxed."),
    "ID": dict(
        name="Idaho", year=2024, confidence="medium",
        brackets=_flat(.05695, zero_up_to={"S": 4_673, "MFJ": 9_346, "HOH": 9_346}),
        std_deduction="federal", exemption=0,
        social_security="exempt", retirement_exclusion=None,
        note="Flat 5.695% above a small zero bracket (2024)."),
    "IL": dict(
        name="Illinois", year=2024, confidence="high",
        brackets=_flat(.0495), std_deduction={"S": 0, "MFJ": 0, "HOH": 0},
        exemption=2_775, social_security="exempt",
        retirement_exclusion=[{"min_age": 0, "per_person": INF}],
        note="Retirement plan distributions and Social Security are exempt. The "
             "exemption phases out above $250k ($500k joint) income."),
    "IN": dict(
        name="Indiana", year=2024, confidence="high",
        brackets=_flat(.0305), std_deduction={"S": 0, "MFJ": 0, "HOH": 0},
        exemption=1_000, social_security="exempt", retirement_exclusion=None,
        note="County income taxes (about 0.5%-3%, typically ~1.5-2%) are not "
             "included."),
    "IA": dict(
        name="Iowa", year=2024, confidence="medium",
        brackets={"S": [(6_210, .044), (31_050, .0482), (INF, .057)],
                  "MFJ": [(12_420, .044), (62_100, .0482), (INF, .057)],
                  "HOH": [(12_420, .044), (62_100, .0482), (INF, .057)]},
        std_deduction="federal", exemption=0, social_security="exempt",
        retirement_exclusion=[{"min_age": 55, "per_person": INF}],
        note="Iowa moves to a flat 3.8% in 2025. Retirement income is exempt at "
             "55+."),
    "KS": dict(
        name="Kansas", year=2024, confidence="medium",
        brackets={"S": [(23_000, .052), (INF, .0558)],
                  "MFJ": [(46_000, .052), (INF, .0558)],
                  "HOH": [(23_000, .052), (INF, .0558)]},
        std_deduction={"S": 3_605, "MFJ": 8_240, "HOH": 6_180},
        exemption={"S": 9_160, "MFJ": 18_320, "HOH": 9_160},
        social_security="exempt", retirement_exclusion=None,
        note="2024 rates from the June 2024 tax cut; Social Security is exempt "
             "from 2024."),
    "KY": dict(
        name="Kentucky", year=2024, confidence="medium",
        brackets=_flat(.04), std_deduction={"S": 3_160, "MFJ": 6_320, "HOH": 3_160},
        exemption=0, social_security="exempt",
        retirement_exclusion=[{"min_age": 0, "per_person": 31_110}],
        note="Flat 4% (3.5% from 2026). Local occupational taxes (often 1-2.5%) "
             "are not included."),
    "LA": dict(
        name="Louisiana", year=2024, confidence="medium",
        brackets={"S": [(12_500, .0185), (50_000, .035), (INF, .0425)],
                  "MFJ": [(25_000, .0185), (100_000, .035), (INF, .0425)],
                  "HOH": [(25_000, .0185), (100_000, .035), (INF, .0425)]},
        std_deduction={"S": 0, "MFJ": 0, "HOH": 0},
        exemption={"S": 4_500, "MFJ": 9_000, "HOH": 9_000},
        social_security="exempt",
        retirement_exclusion=[{"min_age": 65, "per_person": 6_000}],
        note="Louisiana switches to a flat 3% in 2025 with a larger standard "
             "deduction."),
    "ME": dict(
        name="Maine", year=2024, confidence="medium",
        brackets={"S": [(26_050, .058), (61_600, .0675), (INF, .0715)],
                  "MFJ": [(52_100, .058), (123_250, .0675), (INF, .0715)],
                  "HOH": [(39_050, .058), (92_450, .0675), (INF, .0715)]},
        std_deduction="federal", exemption=5_000,
        social_security="exempt", retirement_exclusion=None,
        note="Maine's pension deduction (up to $35k, reduced by Social Security) "
             "is left out, and the deduction/exemption phase-outs for high "
             "incomes too."),
    "MD": dict(
        name="Maryland", year=2024, confidence="medium",
        brackets={
            "S": [(1_000, .02), (2_000, .03), (3_000, .04), (100_000, .0475),
                  (125_000, .05), (150_000, .0525), (250_000, .055), (INF, .0575)],
            "MFJ": [(1_000, .02), (2_000, .03), (3_000, .04), (150_000, .0475),
                    (175_000, .05), (225_000, .0525), (300_000, .055), (INF, .0575)],
            "HOH": [(1_000, .02), (2_000, .03), (3_000, .04), (150_000, .0475),
                    (175_000, .05), (225_000, .0525), (300_000, .055), (INF, .0575)],
        },
        std_deduction={"S": 2_550, "MFJ": 5_150, "HOH": 5_150}, exemption=3_200,
        social_security="exempt",
        retirement_exclusion=[{"min_age": 65, "per_person": 39_500}],
        note="County income tax (2.25%-3.2%, most counties ~3%) is NOT included, "
             "so total Maryland tax is noticeably higher. The pension exclusion "
             "covers employer plans only (here applied to all 401(k)/IRA money)."),
    "MA": dict(
        name="Massachusetts", year=2024, confidence="high",
        brackets=_same([(1_053_750, .05), (INF, .09)]),
        std_deduction={"S": 0, "MFJ": 0, "HOH": 0},
        exemption={"S": 4_400, "MFJ": 8_800, "HOH": 6_800},
        social_security="exempt", retirement_exclusion=None,
        note="5% plus a 4% surtax on income above $1,053,750 (2024). Private "
             "pensions and IRA money are taxed."),
    "MI": dict(
        name="Michigan", year=2024, confidence="medium",
        brackets=_flat(.0425), std_deduction={"S": 0, "MFJ": 0, "HOH": 0},
        exemption=5_600, social_security="exempt", retirement_exclusion=None,
        note="Michigan's retirement-income deduction is being phased back in by "
             "birth year and is left out. City income taxes (e.g. Detroit 2.4%) "
             "are not included."),
    "MN": dict(
        name="Minnesota", year=2024, confidence="medium",
        brackets={"S": [(31_690, .0535), (104_090, .068), (193_240, .0785), (INF, .0985)],
                  "MFJ": [(46_330, .0535), (184_040, .068), (321_450, .0785), (INF, .0985)],
                  "HOH": [(39_010, .0535), (156_760, .068), (256_880, .0785), (INF, .0985)]},
        std_deduction={"S": 14_575, "MFJ": 29_150, "HOH": 21_900}, exemption=0,
        social_security={"exempt_below_agi": {"S": 82_190, "MFJ": 105_380, "HOH": 82_190}},
        retirement_exclusion=None,
        note="Social Security is exempt below the income limits and phased in "
             "above them (modeled as fully taxed above)."),
    "MS": dict(
        name="Mississippi", year=2024, confidence="medium",
        brackets=_same([(10_000, 0.0), (INF, .047)]),
        std_deduction={"S": 2_300, "MFJ": 4_600, "HOH": 3_400},
        exemption={"S": 6_000, "MFJ": 12_000, "HOH": 9_500},
        social_security="exempt",
        retirement_exclusion=[{"min_age": 0, "per_person": INF}],
        note="4.7% above $10,000 in 2024 (falling toward 4%). Retirement income "
             "is exempt once you retire."),
    "MO": dict(
        name="Missouri", year=2024, confidence="medium",
        brackets=_same([(1_273, 0.0), (2_546, .02), (3_819, .025), (5_092, .03),
                        (6_365, .035), (7_638, .04), (8_911, .045), (INF, .048)]),
        std_deduction="federal", exemption=0, social_security="exempt",
        retirement_exclusion=None,
        note="Social Security is exempt from 2024. Kansas City and St. Louis 1% "
             "earnings taxes are not included."),
    "MT": dict(
        name="Montana", year=2024, confidence="medium",
        brackets={"S": [(20_500, .047), (INF, .059)],
                  "MFJ": [(41_000, .047), (INF, .059)],
                  "HOH": [(30_750, .047), (INF, .059)]},
        std_deduction="federal", exemption=0, social_security="taxed",
        retirement_exclusion=None,
        note="Montana taxes Social Security like the federal return; its new "
             "$5,500 subtraction at 65+ and lower capital-gains rates are left "
             "out."),
    "NE": dict(
        name="Nebraska", year=2024, confidence="approx",
        brackets={"S": [(3_880, .0246), (23_370, .0351), (37_670, .0501), (INF, .0584)],
                  "MFJ": [(7_770, .0246), (46_750, .0351), (75_340, .0501), (INF, .0584)],
                  "HOH": [(7_250, .0246), (37_190, .0351), (55_630, .0501), (INF, .0584)]},
        std_deduction={"S": 8_300, "MFJ": 16_600, "HOH": 12_150}, exemption=0,
        social_security="exempt", retirement_exclusion=None,
        note="Standard deduction and head-of-household brackets are best "
             "estimates; the $157 personal credit is left out. Rates are "
             "scheduled to fall to 3.99% by 2027."),
    "NV": _no_tax("Nevada"),
    "NH": _no_tax("New Hampshire",
                  "No tax on wages or retirement income (the old tax on interest "
                  "and dividends ended in 2025)."),
    "NJ": dict(
        name="New Jersey", year=2024, confidence="high",
        brackets={
            "S": [(20_000, .014), (35_000, .0175), (40_000, .035), (75_000, .05525),
                  (500_000, .0637), (1_000_000, .0897), (INF, .1075)],
            "MFJ": [(20_000, .014), (50_000, .0175), (70_000, .0245), (80_000, .035),
                    (150_000, .05525), (500_000, .0637), (1_000_000, .0897), (INF, .1075)],
            "HOH": [(20_000, .014), (50_000, .0175), (70_000, .0245), (80_000, .035),
                    (150_000, .05525), (500_000, .0637), (1_000_000, .0897), (INF, .1075)],
        },
        std_deduction={"S": 0, "MFJ": 0, "HOH": 0}, exemption=1_000,
        social_security="exempt", retirement_exclusion=None, hsa_taxed=True,
        note="New Jersey's pension exclusion for incomes under $150k is left "
             "out. Employee SDI/FLI/UI payroll contributions are not included."),
    "NM": dict(
        name="New Mexico", year=2024, confidence="medium",
        brackets={"S": [(5_500, .017), (11_000, .032), (16_000, .047), (210_000, .049), (INF, .059)],
                  "MFJ": [(8_000, .017), (16_000, .032), (24_000, .047), (315_000, .049), (INF, .059)],
                  "HOH": [(8_000, .017), (16_000, .032), (24_000, .047), (315_000, .049), (INF, .059)]},
        std_deduction="federal", exemption=0,
        social_security={"exempt_below_agi": {"S": 100_000, "MFJ": 150_000, "HOH": 150_000}},
        retirement_exclusion=None,
        note="New brackets start in 2025."),
    "NY": dict(
        name="New York", year=2024, confidence="high",
        brackets={
            "S": [(8_500, .04), (11_700, .045), (13_900, .0525), (80_650, .055),
                  (215_400, .06), (1_077_550, .0685), (5_000_000, .0965),
                  (25_000_000, .103), (INF, .109)],
            "MFJ": [(17_150, .04), (23_600, .045), (27_900, .0525), (161_550, .055),
                    (323_200, .06), (2_155_350, .0685), (5_000_000, .0965),
                    (25_000_000, .103), (INF, .109)],
            "HOH": [(12_800, .04), (17_650, .045), (20_900, .0525), (107_650, .055),
                    (269_300, .06), (1_616_450, .0685), (5_000_000, .0965),
                    (25_000_000, .103), (INF, .109)],
        },
        std_deduction={"S": 8_000, "MFJ": 16_050, "HOH": 11_200}, exemption=0,
        social_security="exempt",
        retirement_exclusion=[{"min_age": 59.5, "per_person": 20_000}],
        note="New York City (3.078%-3.876%) and Yonkers taxes are not included, "
             "nor the recapture of the low brackets above $107,650."),
    "NC": dict(
        name="North Carolina", year=2024, confidence="high",
        brackets=_flat(.045), std_deduction={"S": 12_750, "MFJ": 25_500, "HOH": 19_125},
        exemption=0, social_security="exempt", retirement_exclusion=None,
        note="Flat 4.5% for 2024 (4.25% in 2025)."),
    "ND": dict(
        name="North Dakota", year=2024, confidence="medium",
        brackets={"S": [(47_150, 0.0), (238_200, .0195), (INF, .025)],
                  "MFJ": [(78_775, 0.0), (289_975, .0195), (INF, .025)],
                  "HOH": [(63_100, 0.0), (264_100, .0195), (INF, .025)]},
        std_deduction="federal", exemption=0, social_security="exempt",
        retirement_exclusion=None, ltcg_exclusion=0.40,
        note=""),
    "OH": dict(
        name="Ohio", year=2024, confidence="medium",
        brackets=_same([(26_050, 0.0), (100_000, .0275), (INF, .035)]),
        std_deduction={"S": 0, "MFJ": 0, "HOH": 0}, exemption=1_900,
        social_security="exempt", retirement_exclusion=None,
        note="The personal exemption is income-tested ($1,900-$2,400); the "
             "lowest amount is used. Municipal income taxes (often 1-2.5%) are "
             "not included."),
    "OK": dict(
        name="Oklahoma", year=2024, confidence="medium",
        brackets={"S": [(1_000, .0025), (2_500, .0075), (3_750, .0175), (4_900, .0275),
                        (7_200, .0375), (INF, .0475)],
                  "MFJ": [(2_000, .0025), (5_000, .0075), (7_500, .0175), (9_800, .0275),
                          (12_200, .0375), (INF, .0475)],
                  "HOH": [(2_000, .0025), (5_000, .0075), (7_500, .0175), (9_800, .0275),
                          (12_200, .0375), (INF, .0475)]},
        std_deduction={"S": 6_350, "MFJ": 12_700, "HOH": 9_350}, exemption=1_000,
        social_security="exempt",
        retirement_exclusion=[{"min_age": 0, "per_person": 10_000}],
        note=""),
    "OR": dict(
        name="Oregon", year=2024, confidence="medium",
        brackets={"S": [(4_300, .0475), (10_750, .0675), (125_000, .0875), (INF, .099)],
                  "MFJ": [(8_600, .0475), (21_500, .0675), (250_000, .0875), (INF, .099)],
                  "HOH": [(8_600, .0475), (21_500, .0675), (250_000, .0875), (INF, .099)]},
        std_deduction={"S": 2_745, "MFJ": 5_495, "HOH": 4_420}, exemption=0,
        social_security="exempt", retirement_exclusion=None,
        note="Oregon's deduction for federal tax paid (up to $8,250, gone above "
             "$125k/$250k income) and its $249 personal credit are left out, "
             "which overstates tax below those incomes by up to ~$800. The "
             "Portland-area Metro/Multnomah taxes are not included."),
    "PA": dict(
        name="Pennsylvania", year=2024, confidence="high",
        brackets=_flat(.0307), std_deduction={"S": 0, "MFJ": 0, "HOH": 0},
        exemption=0, social_security="exempt",
        retirement_exclusion=[{"min_age": 59.5, "per_person": INF}],
        pretax_401k_taxed=True,
        note="401(k) contributions are still taxed by Pennsylvania; retirement "
             "income after 59.5 is exempt. Local earned-income taxes (~1%, "
             "Philadelphia 3.75%) are not included."),
    "RI": dict(
        name="Rhode Island", year=2024, confidence="medium",
        brackets=_same([(77_450, .0375), (176_050, .0475), (INF, .0599)]),
        std_deduction={"S": 10_550, "MFJ": 21_150, "HOH": 15_850}, exemption=4_950,
        social_security={"exempt_below_agi": {"S": 101_000, "MFJ": 126_250, "HOH": 101_000}},
        retirement_exclusion=None,
        note="Social Security is exempt at full retirement age under the income "
             "limits (limits approximate). The $20k retirement-income "
             "exclusion is left out."),
    "SC": dict(
        name="South Carolina", year=2024, confidence="medium",
        brackets=_same([(3_460, 0.0), (17_330, .03), (INF, .062)]),
        std_deduction="federal", exemption=0, social_security="exempt",
        retirement_exclusion=[{"min_age": 0, "per_person": 3_000},
                              {"min_age": 65, "per_person": 10_000}],
        ltcg_exclusion=0.44,
        note="Top rate 6.2% for 2024 (falling toward 6%)."),
    "SD": _no_tax("South Dakota"),
    "TN": _no_tax("Tennessee"),
    "TX": _no_tax("Texas"),
    "UT": dict(
        name="Utah", year=2024, confidence="medium",
        brackets=_flat(.0455), std_deduction={"S": 0, "MFJ": 0, "HOH": 0},
        exemption=0, social_security="taxed", retirement_exclusion=None,
        note="Utah's taxpayer credit (which phases out by ~$80k single / $160k "
             "joint) and its Social Security and retirement credits are left "
             "out, so lower incomes are overstated."),
    "VT": dict(
        name="Vermont", year=2024, confidence="medium",
        brackets={"S": [(47_900, .0335), (116_000, .066), (242_000, .076), (INF, .0875)],
                  "MFJ": [(79_950, .0335), (193_300, .066), (294_600, .076), (INF, .0875)],
                  "HOH": [(64_200, .0335), (165_700, .066), (268_300, .076), (INF, .0875)]},
        std_deduction={"S": 7_400, "MFJ": 14_850, "HOH": 11_100}, exemption=5_100,
        social_security={"exempt_below_agi": {"S": 50_000, "MFJ": 65_000, "HOH": 50_000}},
        retirement_exclusion=None,
        note="Social Security is exempt under the income limits and phased in "
             "above them (modeled as fully taxed above)."),
    "VA": dict(
        name="Virginia", year=2024, confidence="high",
        brackets=_same([(3_000, .02), (5_000, .03), (17_000, .05), (INF, .0575)]),
        std_deduction={"S": 8_500, "MFJ": 17_000, "HOH": 8_500}, exemption=930,
        social_security="exempt", retirement_exclusion=None,
        note="The income-tested $12,000 age deduction at 65+ is left out."),
    "WA": _no_tax("Washington",
                  "No tax on wages or retirement income. Washington's 7% tax on "
                  "long-term capital gains above ~$262k a year is not included."),
    "WV": dict(
        name="West Virginia", year=2024, confidence="medium",
        brackets=_same([(10_000, .0236), (25_000, .0315), (40_000, .0354),
                        (60_000, .0472), (INF, .0512)]),
        std_deduction={"S": 0, "MFJ": 0, "HOH": 0}, exemption=2_000,
        social_security="exempt", retirement_exclusion=None,
        note="Social Security becomes fully exempt in 2026 (treated as exempt)."),
    "WI": dict(
        name="Wisconsin", year=2024, confidence="approx",
        brackets={"S": [(14_320, .035), (28_640, .044), (315_310, .053), (INF, .0765)],
                  "MFJ": [(19_090, .035), (38_190, .044), (420_420, .053), (INF, .0765)],
                  "HOH": [(14_320, .035), (28_640, .044), (315_310, .053), (INF, .0765)]},
        std_deduction={"S": 0, "MFJ": 0, "HOH": 0}, exemption=700,
        social_security="exempt", retirement_exclusion=None, ltcg_exclusion=0.30,
        note="Wisconsin's sliding standard deduction (largest at low incomes, "
             "gone by ~$130k single / $150k joint) is left out, so incomes "
             "below that are overstated."),
    "WY": _no_tax("Wyoming"),
}

# States with no tax on wages or retirement income.
NO_INCOME_TAX = tuple(sorted(c for c, row in STATES.items()
                             if all(r == 0.0 for (_, r) in row["brackets"]["S"])))
