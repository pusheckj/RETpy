"""
State income tax tables: all 50 states + DC, tax year 2026.
Brackets and standard deductions follow the BiggerPockets Money Income Tax
Projection Calculator (v1.11.2, captured 2026-11-25) and the state agencies it
cites; California is FTB Tax News, October 2026. See docs/DATA_SOURCES.md for the
rows that differ from that source and why, and docs/data_sources/2026_verification.md.

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
exemption_credits optional nonrefundable credits taken off the bracket tax
                  (config.state_income_tax): {"personal", "senior",
                  "dependent"} dollars per credit -- one personal credit per
                  person on the return, one senior credit per person 65+, one
                  dependent credit per child under 17 -- and a phase-out:
                  "phaseout_agi" {"S"|"MFJ"|"HOH": AGI}, each credit cut by
                  "phaseout_per_step" dollars per "phaseout_step" of AGI above
                  it (a part step counts as a whole one)
surtax            optional {"threshold", "rate"}: an extra rate on taxable
                  income above the threshold, after credits (California's
                  Behavioral Health Services Tax)
note              what is simplified, local taxes left out, known changes

Not modeled anywhere: credits other than the exemption_credits above (child,
earned-income, renter's credits), dependent exemptions, itemized deductions,
alternative minimum taxes, city/county income taxes, and bracket "recapture"
for top earners.
"""

INF = float("inf")

TAX_YEAR = 2026


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
        name="Alabama", year=2026, confidence="approx",
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
        name="Arizona", year=2026, confidence="medium",
        brackets=_flat(.025),
        std_deduction={"S": 8_350, "MFJ": 16_700, "HOH": 8_350}, exemption=0,
        social_security="exempt", retirement_exclusion=None,
        note="Flat 2.5%. Arizona follows federal law as it stood before the 2025 changes "
             "(static conformity), so its standard deduction is $8,350 single / $16,700 joint. "
             "The head-of-household figure is the single amount and may be low. Verify on the "
             "Arizona Department of Revenue 2026 form."),
    "AR": dict(
        name="Arkansas", year=2026, confidence="approx",
        brackets=_same([(5_599, 0.0), (11_199, .02), (15_999, .03), (26_399, .034), (INF, .037)]),
        std_deduction={"S": 2_470, "MFJ": 4_940, "HOH": 2_470},
        exemption=0, social_security="exempt",
        retirement_exclusion=[{"min_age": 59.5, "per_person": 6_000}],
        ltcg_exclusion=0.50,
        note="2026 table: 0% to $5,599, then 2%, 3% and 3.4%, and 3.7% above $26,399 (2026 "
             "special session, retroactive to January 1). Above $94,700 of taxable income "
             "Arkansas uses a second table that adds up to about $290, which is not modeled, so "
             "higher incomes are slightly understated. The $29 personal credit is left out."),
    "CA": dict(
        # 2026 figures: FTB Tax News, October 2026 (3.4% CCPI indexing). The
        # brackets apply to Form 540 taxable income (after the standard
        # deduction). HOH is its own schedule.
        name="California", year=2026, confidence="high",
        brackets={
            "S": [(11_456, .01), (27_157, .02), (42_861, .04), (59_498, .06),
                  (75_197, .08), (384_109, .093), (460_927, .103),
                  (768_213, .113), (INF, .123)],
            "MFJ": [(22_912, .01), (54_314, .02), (85_722, .04), (118_996, .06),
                    (150_394, .08), (768_218, .093), (921_854, .103),
                    (1_536_426, .113), (INF, .123)],
            "HOH": [(22_927, .01), (54_316, .02), (70_018, .04), (86_654, .06),
                    (102_356, .08), (522_385, .093), (626_864, .103),
                    (1_044_771, .113), (INF, .123)],
        },
        std_deduction={"S": 5_900, "MFJ": 11_800, "HOH": 11_800},
        exemption=0,
        # Personal $158 each ($316 joint), senior $158 per person 65+,
        # dependent $491 each. Senior $158 is inferred from the 2025 Form 540
        # (personal, blind and senior all equal). The 2026 phase-out
        # thresholds are ESTIMATES (FTB had not published them): the verified
        # 2025 thresholds (252,203 / 504,411 / 378,310) x 1.034.
        exemption_credits={"personal": 158, "senior": 158, "dependent": 491,
                           "phaseout_agi": {"S": 260_778, "MFJ": 521_561, "HOH": 391_173},
                           "phaseout_step": 2_500, "phaseout_per_step": 6},
        # Behavioral Health Services Tax (formerly the Mental Health Services
        # Tax): 1% of taxable income above $1,000,000, every filing status.
        surtax={"threshold": 1_000_000, "rate": 0.01},
        social_security="exempt", retirement_exclusion=None,
        hsa_taxed=True, payroll={"rate": 0.013, "wage_cap": None},
        note="2026 brackets, standard deduction and exemption credits (personal "
             "$158, senior $158, dependent $491 -- the dependent count is "
             "children under 17), plus the 1% Behavioral Health Services Tax "
             "above $1M of taxable income. The credit phase-out uses estimated "
             "2026 thresholds and treats income after the deduction plus the "
             "deduction as AGI. State Disability Insurance is 1.3% of all "
             "wages (2026 rate, not in the verification report; owner-approved)."),
    "CO": dict(
        name="Colorado", year=2026, confidence="medium",
        brackets=_flat(.044), std_deduction="federal", exemption=0,
        social_security="exempt",
        retirement_exclusion=[{"min_age": 55, "per_person": 20_000},
                              {"min_age": 65, "per_person": 24_000}],
        note="Flat 4.40%, the standing rate; a TABOR refund trigger can lower it in some years. "
             "Social Security is fully deductible at 65+ and partly at 55-64 (treated as exempt)."),
    "CT": dict(
        name="Connecticut", year=2026, confidence="medium",
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
        name="Delaware", year=2026, confidence="medium",
        brackets=_same([(2_000, 0.0), (5_000, .022), (10_000, .039), (20_000, .048),
                        (25_000, .052), (60_000, .0555), (INF, .066)]),
        std_deduction={"S": 3_250, "MFJ": 6_500, "HOH": 3_250}, exemption=0,
        social_security="exempt",
        retirement_exclusion=[{"min_age": 60, "per_person": 12_500}],
        note="The $110 personal credit is left out. Wilmington's 1.25% city "
             "wage tax is not included."),
    "DC": dict(
        name="District of Columbia", year=2026, confidence="high",
        brackets=_same([(10_000, .04), (40_000, .06), (60_000, .065), (250_000, .085),
                        (500_000, .0925), (1_000_000, .0975), (INF, .1075)]),
        std_deduction="federal", exemption=0,
        social_security="exempt", retirement_exclusion=None,
        note=""),
    "FL": _no_tax("Florida"),
    "GA": dict(
        name="Georgia", year=2026, confidence="medium",
        brackets=_flat(.0499), std_deduction={"S": 15_000, "MFJ": 30_000, "HOH": 15_000},
        exemption=0, social_security="exempt",
        retirement_exclusion=[{"min_age": 62, "per_person": 35_000},
                              {"min_age": 65, "per_person": 65_000}],
        note="Flat 4.99% with a $15,000 single / $30,000 joint standard deduction (HB 463, 2026, "
             "retroactive to January 1). Dependent exemptions are left out."),
    "HI": dict(
        name="Hawaii", year=2026, confidence="approx",
        brackets={
            "S": [(9_600, .014), (14_400, .032), (19_200, .055), (24_000, .064), (36_000, .068),
                  (48_000, .072), (125_000, .076), (175_000, .079), (225_000, .0825),
                  (275_000, .09), (325_000, .1), (INF, .11)],
            "MFJ": [(19_200, .014), (28_800, .032), (38_400, .055), (48_000, .064), (72_000, .068),
                    (96_000, .072), (250_000, .076), (350_000, .079), (450_000, .0825),
                    (550_000, .09), (650_000, .1), (INF, .11)],
            "HOH": [(14_400, .014), (21_600, .032), (28_800, .055), (36_000, .064), (54_000, .068),
                    (72_000, .072), (187_500, .076), (262_500, .079), (337_500, .0825),
                    (412_500, .09), (487_500, .1), (INF, .11)],
        },
        std_deduction={"S": 8_000, "MFJ": 16_000, "HOH": 12_000}, exemption=1_144,
        social_security="exempt", retirement_exclusion=None,
        note="2026 brackets and standard deduction ($8,000 single / $16,000 joint / $12,000 head "
             "of household; Act 46). Employer-funded pensions are exempt but 401(k)/IRA money is "
             "taxed."),
    "ID": dict(
        name="Idaho", year=2026, confidence="medium",
        brackets=_flat(.053, zero_up_to={"S": 4_810, "MFJ": 9_620, "HOH": 9_620}),
        std_deduction="federal", exemption=0,
        social_security="exempt", retirement_exclusion=None,
        note="Flat 5.3% above a zero bracket of $4,810 single ($9,620 joint and head of "
             "household), 2026."),
    "IL": dict(
        name="Illinois", year=2026, confidence="high",
        brackets=_flat(.0495), std_deduction={"S": 0, "MFJ": 0, "HOH": 0},
        exemption=2_775, social_security="exempt",
        retirement_exclusion=[{"min_age": 0, "per_person": INF}],
        note="Retirement plan distributions and Social Security are exempt. The "
             "exemption phases out above $250k ($500k joint) income."),
    "IN": dict(
        name="Indiana", year=2026, confidence="high",
        brackets=_flat(.0295), std_deduction={"S": 0, "MFJ": 0, "HOH": 0},
        exemption=1_000, social_security="exempt", retirement_exclusion=None,
        note="County income taxes (about 0.5%-3%, typically ~1.5-2%) are not "
             "included."),
    "IA": dict(
        name="Iowa", year=2026, confidence="medium",
        brackets=_flat(.038),
        std_deduction="federal", exemption=0, social_security="exempt",
        retirement_exclusion=[{"min_age": 55, "per_person": INF}],
        note="Flat 3.8% since 2025. Retirement income is exempt at 55+."),
    "KS": dict(
        name="Kansas", year=2026, confidence="medium",
        brackets={"S": [(23_000, .052), (INF, .0558)],
                  "MFJ": [(46_000, .052), (INF, .0558)],
                  "HOH": [(23_000, .052), (INF, .0558)]},
        std_deduction={"S": 3_605, "MFJ": 8_240, "HOH": 6_180},
        exemption={"S": 9_160, "MFJ": 18_320, "HOH": 9_160},
        social_security="exempt", retirement_exclusion=None,
        note="Rates from the 2024 tax cut, still in force. Social Security is exempt."),
    "KY": dict(
        name="Kentucky", year=2026, confidence="medium",
        brackets=_flat(.035), std_deduction={"S": 3_360, "MFJ": 6_720, "HOH": 3_360},
        exemption=0, social_security="exempt",
        retirement_exclusion=[{"min_age": 0, "per_person": 31_110}],
        note="Flat 3.5% for 2026. The $3,360 standard deduction is per taxpayer, and a joint "
             "return is given two. Local occupational taxes (often 1-2.5%) are not included."),
    "LA": dict(
        name="Louisiana", year=2026, confidence="medium",
        brackets=_flat(.03),
        std_deduction={"S": 12_875, "MFJ": 25_750, "HOH": 25_750},
        exemption=0, social_security="exempt",
        retirement_exclusion=[{"min_age": 65, "per_person": 6_000}],
        note="Flat 3% since the 2025 reform, which replaced the personal exemption with a "
             "larger standard deduction ($12,875 single / $25,750 joint and head of household). "
             "Dependent deductions are left out."),
    "ME": dict(
        name="Maine", year=2026, confidence="medium",
        brackets={
            "S": [(27_400, .058), (64_850, .0675), (1_000_000, .0715), (INF, .0915)],
            "MFJ": [(54_850, .058), (129_750, .0675), (1_500_000, .0715), (INF, .0915)],
            "HOH": [(41_100, .058), (97_300, .0675), (1_500_000, .0715), (INF, .0915)],
        },
        std_deduction={"S": 15_700, "MFJ": 31_400, "HOH": 23_550}, exemption=5_000,
        social_security="exempt", retirement_exclusion=None,
        note="2026 brackets and standard deduction ($15,700 single / $31,400 joint / $23,550 head "
             "of household). The new 2% surcharge above $1 million single ($1.5 million joint and "
             "head of household) is modeled as a 9.15% top rate. Maine's pension deduction (up to "
             "$35k, reduced by Social Security) is left out, and the deduction/exemption "
             "phase-outs for high incomes too."),
    "MD": dict(
        name="Maryland", year=2026, confidence="medium",
        brackets={
            "S": [(1_000, .02), (2_000, .03), (3_000, .04), (100_000, .0475), (125_000, .05),
                  (150_000, .0525), (250_000, .055), (500_000, .0575), (1_000_000, .0625),
                  (INF, .065)],
            "MFJ": [(1_000, .02), (2_000, .03), (3_000, .04), (150_000, .0475), (175_000, .05),
                    (225_000, .0525), (300_000, .055), (600_000, .0575), (1_200_000, .0625),
                    (INF, .065)],
            "HOH": [(1_000, .02), (2_000, .03), (3_000, .04), (150_000, .0475), (175_000, .05),
                    (225_000, .0525), (300_000, .055), (600_000, .0575), (1_200_000, .0625),
                    (INF, .065)],
        },
        std_deduction={"S": 3_350, "MFJ": 6_700, "HOH": 6_700}, exemption=3_200,
        social_security="exempt",
        retirement_exclusion=[{"min_age": 65, "per_person": 39_500}],
        note="2026 adds 6.25% and 6.5% rates on very high incomes. County income tax (2.25%-3.2%, "
             "most counties ~3%) is NOT included, so total Maryland tax is noticeably higher. The "
             "pension exclusion covers employer plans only (here applied to all 401(k)/IRA "
             "money)."),
    "MA": dict(
        name="Massachusetts", year=2026, confidence="high",
        brackets=_same([(1_107_750, .05), (INF, .09)]),
        std_deduction={"S": 0, "MFJ": 0, "HOH": 0},
        exemption={"S": 4_400, "MFJ": 8_800, "HOH": 6_800},
        social_security="exempt", retirement_exclusion=None,
        note="5% plus a 4% surtax on income above $1,107,750 (2026). Private pensions and IRA "
             "money are taxed."),
    "MI": dict(
        name="Michigan", year=2026, confidence="medium",
        brackets=_flat(.0425), std_deduction={"S": 0, "MFJ": 0, "HOH": 0},
        exemption=5_600, social_security="exempt", retirement_exclusion=None,
        note="Michigan's retirement-income deduction is being phased back in by "
             "birth year and is left out. City income taxes (e.g. Detroit 2.4%) "
             "are not included."),
    "MN": dict(
        name="Minnesota", year=2026, confidence="medium",
        brackets={
            "S": [(33_310, .0535), (109_430, .068), (203_150, .0785), (INF, .0985)],
            "MFJ": [(48_700, .0535), (193_480, .068), (337_930, .0785), (INF, .0985)],
            "HOH": [(39_010, .0535), (156_760, .068), (256_880, .0785), (INF, .0985)],
        },
        std_deduction={"S": 15_300, "MFJ": 30_600, "HOH": 21_900}, exemption=0,
        social_security={"exempt_below_agi": {"S": 82_190, "MFJ": 105_380, "HOH": 82_190}},
        retirement_exclusion=None,
        note="Social Security is exempt below the income limits and phased in above them (modeled "
             "as fully taxed above). Head-of-household brackets and deduction are the 2024 "
             "figures, not updated for 2026."),
    "MS": dict(
        name="Mississippi", year=2026, confidence="medium",
        brackets=_same([(10_000, 0.0), (INF, .04)]),
        std_deduction={"S": 2_300, "MFJ": 4_600, "HOH": 3_400},
        exemption={"S": 6_000, "MFJ": 12_000, "HOH": 9_500},
        social_security="exempt",
        retirement_exclusion=[{"min_age": 0, "per_person": INF}],
        note="4% above $10,000 (2026). Retirement income is exempt once you retire."),
    "MO": dict(
        name="Missouri", year=2026, confidence="medium",
        brackets=_same([(1_348, 0.0), (2_696, .02), (4_044, .025), (5_392, .03), (6_740, .035),
                        (8_088, .04), (9_436, .045), (INF, .047)]),
        std_deduction="federal", exemption=0, social_security="exempt",
        retirement_exclusion=None,
        note="Social Security is exempt. Kansas City and St. Louis 1% earnings taxes are not "
             "included."),
    "MT": dict(
        name="Montana", year=2026, confidence="medium",
        brackets={
            "S": [(47_500, .047), (INF, .0565)],
            "MFJ": [(95_000, .047), (INF, .0565)],
            "HOH": [(71_250, .047), (INF, .0565)],
        },
        std_deduction="federal", exemption=0, social_security="taxed",
        retirement_exclusion=None,
        note="2026 brackets: 4.7% up to $47,500 single ($95,000 joint, $71,250 head of "
             "household) and 5.65% above. Montana taxes Social Security like the federal "
             "return; its new $5,500 subtraction at 65+ and lower capital-gains rates are left "
             "out."),
    "NE": dict(
        name="Nebraska", year=2026, confidence="approx",
        brackets={
            "S": [(4_130, .0246), (24_760, .0351), (INF, .0455)],
            "MFJ": [(8_250, .0246), (49_530, .0351), (INF, .0455)],
            "HOH": [(7_250, .0246), (37_190, .0351), (INF, .0455)],
        },
        std_deduction={"S": 8_850, "MFJ": 17_700, "HOH": 12_150}, exemption=0,
        social_security="exempt", retirement_exclusion=None,
        note="2026 rates: 2.46%, 3.51% and 4.55% on top (scheduled to fall to 3.99% by 2027). "
             "Head-of-household brackets use the 2024 thresholds with the 2026 rates, and its "
             "deduction is the 2024 figure. The $157 personal credit is left out."),
    "NV": _no_tax("Nevada"),
    "NH": _no_tax("New Hampshire",
                  "No tax on wages or retirement income (the old tax on interest "
                  "and dividends ended in 2025)."),
    "NJ": dict(
        name="New Jersey", year=2026, confidence="high",
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
        name="New Mexico", year=2026, confidence="medium",
        brackets={
            "S": [(5_500, .015), (16_500, .032), (33_500, .043), (66_500, .047), (210_000, .049),
                  (INF, .059)],
            "MFJ": [(8_000, .015), (25_000, .032), (50_000, .043), (100_000, .047), (315_000, .049),
                    (INF, .059)],
            "HOH": [(8_000, .015), (25_000, .032), (50_000, .043), (100_000, .047), (315_000, .049),
                    (INF, .059)],
        },
        std_deduction="federal", exemption=0,
        social_security={"exempt_below_agi": {"S": 100_000, "MFJ": 150_000, "HOH": 150_000}},
        retirement_exclusion=None,
        note="The 2025 brackets (1.5% to 5.9%) are in force."),
    "NY": dict(
        name="New York", year=2026, confidence="high",
        brackets={
            "S": [(8_500, .039), (11_700, .044), (13_900, .0515), (80_650, .054), (215_400, .059),
                  (1_077_550, .0685), (5_000_000, .0965), (25_000_000, .103), (INF, .109)],
            "MFJ": [(17_150, .039), (23_600, .044), (27_900, .0515), (161_550, .054),
                    (323_200, .059), (2_155_350, .0685), (5_000_000, .0965), (25_000_000, .103),
                    (INF, .109)],
            "HOH": [(12_800, .039), (17_650, .044), (20_900, .0515), (107_650, .054),
                    (269_300, .059), (1_616_450, .0685), (5_000_000, .0965), (25_000_000, .103),
                    (INF, .109)],
        },
        std_deduction={"S": 8_000, "MFJ": 16_050, "HOH": 11_200}, exemption=0,
        social_security="exempt",
        retirement_exclusion=[{"min_age": 59.5, "per_person": 20_000}],
        note="New York City (3.078%-3.876%) and Yonkers taxes are not included, "
             "nor the recapture of the low brackets above $107,650."),
    "NC": dict(
        name="North Carolina", year=2026, confidence="high",
        brackets=_flat(.0399), std_deduction={"S": 12_750, "MFJ": 25_500, "HOH": 19_125},
        exemption=0, social_security="exempt", retirement_exclusion=None,
        note="Flat 3.99% for 2026."),
    "ND": dict(
        name="North Dakota", year=2026, confidence="medium",
        brackets={
            "S": [(48_475, 0.0), (244_825, .0195), (INF, .025)],
            "MFJ": [(80_975, 0.0), (298_075, .0195), (INF, .025)],
            "HOH": [(63_100, 0.0), (264_100, .0195), (INF, .025)],
        },
        std_deduction="federal", exemption=0, social_security="exempt",
        retirement_exclusion=None, ltcg_exclusion=0.40,
        note="Head-of-household brackets are the 2024 figures, not updated for 2026."),
    "OH": dict(
        name="Ohio", year=2026, confidence="medium",
        brackets=_same([(26_050 - 332 / .0275, 0.0), (INF, .0275)]),
        std_deduction={"S": 0, "MFJ": 0, "HOH": 0}, exemption=1_900,
        social_security="exempt", retirement_exclusion=None,
        note="Ohio taxes nothing up to $26,050, then $332 plus 2.75% of the excess. The brackets "
             "here start 2.75% at $13,977. That matches the formula above $26,050 and overstates "
             "tax by up to $332 between $13,977 and $26,050. The personal exemption is "
             "income-tested ($1,900-$2,400); the lowest amount is used. Municipal income taxes "
             "(often 1-2.5%) are not included."),
    "OK": dict(
        name="Oklahoma", year=2026, confidence="medium",
        brackets={
            "S": [(3_750, 0.0), (4_900, .025), (7_200, .035), (INF, .045)],
            "MFJ": [(7_500, 0.0), (9_800, .025), (14_400, .035), (INF, .045)],
            "HOH": [(7_500, 0.0), (9_800, .025), (14_400, .035), (INF, .045)],
        },
        std_deduction={"S": 6_350, "MFJ": 12_700, "HOH": 9_350}, exemption=1_000,
        social_security="exempt",
        retirement_exclusion=[{"min_age": 0, "per_person": 10_000}],
        note="2026 rates: 2.5%, 3.5% and 4.5%. Head of household uses the joint brackets and its "
             "2024 standard deduction."),
    "OR": dict(
        name="Oregon", year=2026, confidence="medium",
        brackets={
            "S": [(4_550, .0475), (11_400, .0675), (125_000, .0875), (INF, .099)],
            "MFJ": [(9_100, .0475), (22_800, .0675), (250_000, .0875), (INF, .099)],
            "HOH": [(9_100, .0475), (22_800, .0675), (250_000, .0875), (INF, .099)],
        },
        std_deduction={"S": 2_910, "MFJ": 5_820, "HOH": 4_420}, exemption=0,
        social_security="exempt", retirement_exclusion=None,
        note="2026 brackets and standard deduction; head of household uses the joint brackets and "
             "its 2024 deduction. Oregon's deduction for federal tax paid (up to $8,250, gone "
             "above $125k/$250k income) and its $249 personal credit are left out, which "
             "overstates tax below those incomes by up to ~$800. The Portland-area "
             "Metro/Multnomah taxes are not included."),
    "PA": dict(
        name="Pennsylvania", year=2026, confidence="high",
        brackets=_flat(.0307), std_deduction={"S": 0, "MFJ": 0, "HOH": 0},
        exemption=0, social_security="exempt",
        retirement_exclusion=[{"min_age": 59.5, "per_person": INF}],
        pretax_401k_taxed=True,
        note="401(k) contributions are still taxed by Pennsylvania; retirement "
             "income after 59.5 is exempt. Local earned-income taxes (~1%, "
             "Philadelphia 3.75%) are not included."),
    "RI": dict(
        name="Rhode Island", year=2026, confidence="medium",
        brackets=_same([(82_050, .0375), (186_450, .0475), (INF, .0599)]),
        std_deduction={"S": 11_200, "MFJ": 22_400, "HOH": 16_800}, exemption=4_950,
        social_security={"exempt_below_agi": {"S": 101_000, "MFJ": 126_250, "HOH": 101_000}},
        retirement_exclusion=None,
        note="Social Security is exempt at full retirement age under the income "
             "limits (limits approximate). The $20k retirement-income "
             "exclusion is left out."),
    "SC": dict(
        name="South Carolina", year=2026, confidence="approx",
        brackets=_same([(30_000, .0199), (INF, .0521)]),
        std_deduction={"S": 15_000, "MFJ": 30_000, "HOH": 22_500}, exemption=0,
        social_security="exempt",
        retirement_exclusion=[{"min_age": 0, "per_person": 3_000},
                              {"min_age": 65, "per_person": 10_000}],
        ltcg_exclusion=0.44,
        note="2026 rates: 1.99% up to $30,000 and 5.21% above (H.4216, retroactive to January 1). "
             "The SCIAD deduction ($15,000 single / $30,000 joint / $22,500 head of household) "
             "shrinks to zero between $40,000 and $95,000 of single income; that phase-out is not "
             "modeled, so tax is understated above $40,000 (by up to about $780 single / $1,560 "
             "joint)."),
    "SD": _no_tax("South Dakota"),
    "TN": _no_tax("Tennessee"),
    "TX": _no_tax("Texas"),
    "UT": dict(
        name="Utah", year=2026, confidence="approx",
        brackets=_flat(.0445), std_deduction={"S": 0, "MFJ": 0, "HOH": 0},
        exemption=0, social_security="taxed", retirement_exclusion=None,
        note="4.45% flat (SB 60, 2026, retroactive to January 1). Utah's taxpayer credit (6% of "
             "the federal deduction, cut by 1.3 cents for each dollar of income above $18,696 "
             "single / $37,392 joint) and its Social Security and retirement credits are left "
             "out, so lower incomes are overstated by up to about $1,900."),
    "VT": dict(
        name="Vermont", year=2026, confidence="medium",
        brackets={
            "S": [(49_400, .0335), (119_700, .066), (249_700, .076), (INF, .0875)],
            "MFJ": [(82_500, .0335), (199_450, .066), (304_000, .076), (INF, .0875)],
            "HOH": [(64_200, .0335), (165_700, .066), (268_300, .076), (INF, .0875)],
        },
        std_deduction={"S": 7_650, "MFJ": 15_300, "HOH": 11_100}, exemption=5_100,
        social_security={"exempt_below_agi": {"S": 50_000, "MFJ": 65_000, "HOH": 50_000}},
        retirement_exclusion=None,
        note="Social Security is exempt under the income limits and phased in above them (modeled "
             "as fully taxed above). Head-of-household brackets and deduction are the 2024 "
             "figures, not updated for 2026."),
    "VA": dict(
        name="Virginia", year=2026, confidence="high",
        brackets=_same([(3_000, .02), (5_000, .03), (17_000, .05), (INF, .0575)]),
        std_deduction={"S": 8_750, "MFJ": 17_500, "HOH": 8_750}, exemption=930,
        social_security="exempt", retirement_exclusion=None,
        note="The income-tested $12,000 age deduction at 65+ is left out."),
    "WA": _no_tax("Washington",
                  "No tax on wages or retirement income. Washington's 7% tax on "
                  "long-term capital gains above ~$262k a year is not included."),
    "WV": dict(
        name="West Virginia", year=2026, confidence="medium",
        brackets=_same([(10_000, .0211), (25_000, .0281), (40_000, .0316), (60_000, .0422),
                        (INF, .0458)]),
        std_deduction={"S": 0, "MFJ": 0, "HOH": 0}, exemption=2_000,
        social_security="exempt", retirement_exclusion=None,
        note="All rates cut 5% for 2026, top rate 4.58% (SB 392, retroactive to January 1). "
             "Social Security is exempt."),
    "WI": dict(
        name="Wisconsin", year=2026, confidence="approx",
        brackets={
            "S": [(15_110, .035), (51_950, .044), (332_720, .053), (INF, .0765)],
            "MFJ": [(20_150, .035), (69_260, .044), (443_630, .053), (INF, .0765)],
            "HOH": [(15_110, .035), (51_950, .044), (332_720, .053), (INF, .0765)],
        },
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
