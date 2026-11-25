#!/usr/bin/env python3
"""Dev-only tax cross-check: RETpy's tax math against the BPM tax engine.

    python3 tools/tax_crosscheck/crosscheck.py --bpm-source /path/to/calc_tax.html

Runs identical scenarios through BiggerPockets Money's BPMTaxEngine.compute (Node, no
DOM) and through RETpy (one fresh Python process per fixture, app_side.py), compares
the federal ordinary tax, long-term capital-gains tax, NIIT, state tax and a few other
figures to the cent, buckets every difference, and writes REPORT.md.

This process never imports retirement_sim, so it cannot change the app's config: every
fixture's config changes live and die in its own child process. See README.md.
"""
import argparse
import concurrent.futures as cf
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TOL = 0.005                      # "to the cent"
KEY = {"S": "single", "MFJ": "mfj", "HOH": "hoh"}
LABEL = {"S": "Single", "MFJ": "MFJ", "HOH": "HoH"}

# States in the default grid: CA, a no-tax state (TX), flat taxes (PA, IL), a high-tax
# state (NJ), and every state whose 2026 table differs from the 2024 one or from BPM.
GRID_STATES = ("CA TX PA IL NJ AL AR AZ CO GA HI IA ID IN KY LA MA MD ME MN MO MS MT NC ND "
               "NE NM NY OH OK OR RI SC UT VA VT WI WV").split()
QUICK_STATES = "CA TX NY GA OH SC".split()

# Known reasons a state's NEUTRAL result (RETpy with its app-only rules switched off)
# still differs from BPM: (bucket, reason, statuses or None for all, sign, largest gap).
# ``sign`` is the expected sign of RETpy minus BPM (None = either way) and the gap limit
# is a little above the largest difference the cause can produce, so a typo in one of
# these rows is not hidden behind its waiver.
HOH_COPY = ("BPM lists Single's figures for head of household; RETpy keeps a real "
            "head-of-household schedule")
STATE_KNOWN = {
    "AL": ("modeling difference", "BPM takes the top-of-range deduction; RETpy uses the "
           "income-tested floor", None, +1, 200),
    "WI": ("modeling difference", "BPM takes the full standard deduction; RETpy leaves the "
           "sliding deduction out (0)", None, +1, 2_000),
    "KY": ("BPM simplification", "BPM gives a joint return one $3,360 deduction; Kentucky "
           "gives each taxpayer one", {"MFJ"}, -1, 120),
    "OH": ("modeling difference", "RETpy smooths Ohio's $332 base amount into a 2.75% rate "
           "from $13,977; exact above $26,050", None, +1, 333),
    "AR": ("modeling difference", "RETpy omits Arkansas's second table above $94,700 "
           "(adds up to about $290)", None, -1, 300),
    "UT": ("modeling difference", "RETpy omits Utah's taxpayer credit", None, +1, 2_000),
    "SC": ("modeling difference", "RETpy omits the SCIAD phase-out (BPM models it)", None,
           -1, 1_600),
}
for _c in ("MN", "ND", "NE", "VT", "OK", "OR", "ID", "MT", "LA"):
    STATE_KNOWN[_c] = ("BPM simplification", HOH_COPY, {"HOH"}, None, 2_500)
RULE_TEXT = {
    "exemption": "personal exemption (BPM does not model it)",
    "retirement_exclusion": "retirement-income exclusion (BPM taxes it all)",
    "ltcg_exclusion": "state capital-gains exclusion (BPM taxes gains in full)",
    "social_security": "state taxes Social Security (BPM exempts it everywhere)",
    "credits": "exemption credits (BPM does not model them)",
}
PRIORITY = {"RETpy bug": 3, "modeling difference": 2, "BPM simplification": 1, "match": 0}


# ----------------------------------------------------------------------------- fixtures
def _fx(**kw):
    kw.setdefault("tags", [])
    kw.setdefault("expect", "match")
    kw.setdefault("retirement", True)
    return kw


def build_fixtures(states):
    fixtures = []
    levels = {  # status -> (W2 low, W2 high, ordinary, ltcg, SS-mix ordinary, ltcg, ss)
        "S": (90_000, 275_000, 60_000, 40_000, 35_000, 20_000, 30_000),
        "MFJ": (180_000, 550_000, 120_000, 80_000, 70_000, 40_000, 55_000),
        "HOH": (90_000, 275_000, 75_000, 50_000, 35_000, 20_000, 30_000),
    }
    for state in states:
        for st, (lo, hi, o, g, o3, g3, ss3) in levels.items():
            base = dict(status=st, state=state, group="grid")
            tag = f"{state}-{st}"
            fixtures.append(_fx(id=f"{tag}-W2-low", mix="W2", age=45, wages=lo,
                                label=f"W-2 ${lo:,}", **base))
            fixtures.append(_fx(id=f"{tag}-W2-high", mix="W2", age=45, wages=hi,
                                label=f"W-2 ${hi:,}", **base))
            fixtures.append(_fx(id=f"{tag}-ORD-LTCG", mix="ORD_LTCG", age=62, ordinary=o,
                                ltcg=g, label=f"IRA/pension ${o:,} + LTCG ${g:,}", **base))
            fixtures.append(_fx(id=f"{tag}-ORD-LTCG-SS", mix="ORD_LTCG_SS", age=70,
                                ordinary=o3, ltcg=g3, ss=ss3,
                                label=f"pension ${o3:,} + LTCG ${g3:,} + SS ${ss3:,}", **base))
    fixtures += edge_fixtures()
    return fixtures


def edge_fixtures():
    out = []

    def add(id_, label, mix, st, age, expect="match", tags=(), state="TX", **amounts):
        out.append(_fx(id="EDGE-" + id_, group="edge", label=label, mix=mix, status=st,
                       state=state, age=age, expect=expect, tags=list(tags), **amounts))
    # NIIT threshold crossing (200k Single / HoH, 250k MFJ)
    add("niit-S-below", "NIIT: Single MAGI 199,000 (below)", "ORD_LTCG", "S", 62,
        ordinary=179_000, ltcg=20_000)
    add("niit-S-at", "NIIT: Single MAGI exactly 200,000", "ORD_LTCG", "S", 62,
        ordinary=180_000, ltcg=20_000)
    add("niit-S-cross", "NIIT: Single MAGI 210,000 (crosses, partial)", "ORD_LTCG", "S", 62,
        ordinary=190_000, ltcg=20_000)
    add("niit-S-full", "NIIT: Single MAGI 300,000 (gains fully inside)", "ORD_LTCG", "S", 62,
        ordinary=250_000, ltcg=50_000)
    add("niit-MFJ-cross", "NIIT: MFJ MAGI 270,000 (crosses, partial)", "ORD_LTCG", "MFJ", 62,
        ordinary=240_000, ltcg=30_000)
    add("niit-HOH-cross", "NIIT: HoH MAGI 210,000 (crosses, partial)", "ORD_LTCG", "HOH", 62,
        ordinary=190_000, ltcg=20_000)
    add("niit-S-ss-order", "NIIT: Single, Social Security pushes MAGI over 200,000",
        "ORD_LTCG_SS", "S", 70, tags=["ss_order"],
        ordinary=150_000, ltcg=40_000, ss=40_000)
    # IRMAA tier boundaries (MAGI = AGI)
    for st, bounds in (("S", (109_000, 137_000, 500_000)), ("MFJ", (218_000, 274_000, 750_000))):
        for b in bounds:
            for delta, name in ((0, "at"), (1, "over")):
                top = b in (500_000, 750_000)
                add(f"irmaa-{st}-{b}-{name}", f"IRMAA: {LABEL[st]} MAGI {b + delta:,}",
                    "ORD", st, 62, ordinary=b + delta + 0.0,
                    expect="gap" if (top and delta == 0) else "match",
                    tags=["irmaa_top"] if (top and delta == 0) else [])
    # Senior deduction phase-out: $6,000 per person 65+, 6% over 75k / 150k MAGI
    for st, pts, age in (("S", (75_000, 100_000, 175_000, 200_000), 67),
                         ("MFJ", (150_000, 200_000, 250_000, 300_000), 67),
                         ("HOH", (75_000, 100_000, 175_000), 67)):
        for m in pts:
            add(f"senior-{st}-{m}", f"Senior deduction: {LABEL[st]} age {age}+, MAGI {m:,}",
                "ORD", st, age, ordinary=float(m))
    add("senior-S-cap-ltcg", "Senior deduction in phase-out with gains (Single 67, 90k + 30k LTCG)",
        "ORD_LTCG", "S", 67, tags=["senior_order"], ordinary=90_000, ltcg=30_000)
    # Head of household 24% / 32% bracket tops (BPM tops the 24% band at 201,775)
    add("hoh-24-top", "HoH: taxable income 201,760 (24% band tops at 201,750 by statute)",
        "ORD", "HOH", 62, expect="gap", tags=["hoh_boundary"], ordinary=201_760 + 24_150.0)
    add("hoh-24-below", "HoH: taxable income 201,700", "ORD", "HOH", 62,
        ordinary=201_700 + 24_150.0)
    add("hoh-32-top", "HoH: taxable income 256,200 to 256,300", "ORD", "HOH", 62,
        ordinary=256_300 + 24_150.0)
    add("single-24-top", "Single: taxable income 201,780 (24% band tops at 201,775)", "ORD",
        "S", 62, ordinary=201_780 + 16_100.0)
    # Capital-gains stacking
    add("ltcg-0pct", "LTCG wholly in the 0% band (Single 30k + 30k)", "ORD_LTCG", "S", 62,
        ordinary=30_000, ltcg=30_000)
    add("ltcg-straddle", "LTCG straddling the 0% / 15% line (Single 45k + 30k)", "ORD_LTCG", "S",
        62, ordinary=45_000, ltcg=30_000)
    add("ltcg-low-ordinary", "Ordinary below the standard deduction, large gain (Single 10k + 60k)",
        "ORD_LTCG", "S", 62, tags=["std_unused"], ordinary=10_000, ltcg=60_000)
    add("ltcg-no-ordinary", "Gain only (MFJ 0 + 150k)", "ORD_LTCG", "MFJ", 62,
        tags=["std_unused"], ordinary=0.0, ltcg=150_000)
    add("ltcg-20pct", "LTCG in the 20% band (Single 400k + 300k)", "ORD_LTCG", "S", 62,
        ordinary=400_000, ltcg=300_000)
    # Social Security taxability
    add("ss-zero", "SS below the first base (Single pension 10k + SS 20k)", "ORD_SS", "S", 70,
        ordinary=10_000, ss=20_000)
    add("ss-half", "SS in the 50% tier (Single pension 20k + SS 24k)", "ORD_SS", "S", 70,
        ordinary=20_000, ss=24_000)
    add("ss-85", "SS in the 85% tier (Single pension 50k + SS 36k)", "ORD_SS", "S", 70,
        ordinary=50_000, ss=36_000)
    add("ss-85-MFJ", "SS in the 85% tier (MFJ pension 80k + SS 60k)", "ORD_SS", "MFJ", 70,
        ordinary=80_000, ss=60_000)
    add("ss-ltcg-order", "Gains with SS (Single 67: pension 35k + LTCG 20k + SS 30k)",
        "ORD_LTCG_SS", "S", 67, tags=["ss_order"], ordinary=35_000, ltcg=20_000,
        ss=30_000)
    # CA payroll tax and a high wage (wage base, Additional Medicare)
    add("ca-sdi", "CA SDI on W-2 wages (Single 150k)", "W2", "S", 45, state="CA", wages=150_000)
    add("wage-base-MFJ", "MFJ one earner 400k (over the 184,500 wage base)", "W2", "MFJ", 45,
        wages=400_000)
    return out


# ------------------------------------------------------------------------- BPM mapping
def bpm_input(fx, std_extra=0.0, state=None):
    lines = []
    if fx["mix"] == "W2":
        lines.append({"type": "w2", "amount": fx["wages"], "earner": 1})
    if fx.get("ordinary"):
        lines.append({"type": "retirement", "amount": fx["ordinary"], "earner": 1})
    if fx.get("ltcg"):
        lines.append({"type": fx.get("gain_type", "ltcg"), "amount": fx["ltcg"], "earner": 1})
    if fx.get("ss"):
        lines.append({"type": "ss", "amount": fx["ss"], "earner": 1})
    return {"filing": KEY[fx["status"]], "incomeLines": lines, "deferrals": 0,
            "ficaDeferrals": 0, "seDeferrals": 0, "seHealthIns": 0,
            "otherDeductions": round(std_extra, 2) if std_extra else 0, "foreignIncome": 0,
            "children": 0, "state": state or fx["state"], "deductionMethod": "standard",
            "itemized": {"salt": 0, "mortgage": 0, "charitable": 0, "medical": 0, "other": 0},
            "qbi": {"sstb": False, "w2paid": 0, "ubia": 0}, "rentalActive": False,
            "household": 2 if fx["status"] == "MFJ" else 1, "region": "contig",
            "acaAddbacks": 0}


# ---------------------------------------------------------------------------- runners
def run_app(fx, env):
    proc = subprocess.run([sys.executable, os.path.join(HERE, "app_side.py"), json.dumps(fx)],
                          capture_output=True, text=True, env=env, cwd=HERE)
    if proc.returncode:
        raise RuntimeError(f"app_side failed for {fx['id']}:\n{proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


def run_apps(fixtures, workers):
    env = dict(os.environ, RETIREMENT_SIM_PROFILE="/nonexistent/tax-crosscheck-profile.json")
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda fx: run_app(fx, env), fixtures))


def run_bpm(source, items, work):
    fx_path, out_path = os.path.join(work, "bpm_in.json"), os.path.join(work, "bpm_out.json")
    with open(fx_path, "w") as fh:
        json.dump(items, fh)
    subprocess.run(["node", os.path.join(HERE, "bpm_runner.mjs"), source, fx_path, out_path],
                   check=True)
    with open(out_path) as fh:
        res = {r["id"]: r for r in json.load(fh)}
    bad = [i for i, r in res.items() if not r["ok"]]
    if bad:
        raise RuntimeError(f"BPM engine failed on {bad[:3]}: {res[bad[0]]['error'][:500]}")
    return {i: r["result"] for i, r in res.items()}


# ------------------------------------------------------------------- default example
DEFAULT_REFERENCE = {   # verified to the cent (bpm-raw-data/tax/verification.json)
    "SE tax": (1130.36, lambda r: r["se"]["seTax"]),
    "AGI": (178434.82, lambda r: r["income"]["agi"]),
    "QBI deduction": (1486.96, lambda r: r["deductions"]["qbi"]),
    "Taxable income": (144747.85, lambda r: r["income"]["taxableIncome"]),
    "Federal ordinary tax": (19728.53, lambda r: r["federal"]["fedOrdinary"]),
    "LTCG tax": (1050.00, lambda r: r["federal"]["ltcgTax"]),
    "W-2 FICA": (12775.50, lambda r: r["payroll"]["w2FICA"]),
    "CO state tax": (6368.91, lambda r: r["state"]["stateTax"]),
    "Child tax credit": (4400.00, lambda r: r["credits"]["ctc"]),
    "All-in tax": (36653.30, lambda r: r["totals"]["allIn"]),
    "Take-home": (142346.70, lambda r: r["totals"]["netHome"]),
}


def default_example(source, work, env):
    inp = {"filing": "mfj", "incomeLines": [
        {"type": "w2", "amount": 100000, "earner": 1}, {"type": "w2", "amount": 67000, "earner": 2},
        {"type": "se", "amount": 3000, "earner": 1}, {"type": "se", "amount": 5000, "earner": 2},
        {"type": "other", "amount": 2000, "earner": 1},
        {"type": "rental", "amount": 10000, "earner": 1},
        {"type": "ltcg", "amount": 7000, "earner": 1}],
        "deferrals": 15000, "ficaDeferrals": 0, "seDeferrals": 0, "seHealthIns": 0,
        "otherDeductions": 0, "foreignIncome": 0, "children": 2, "state": "CO",
        "deductionMethod": "standard",
        "itemized": {"salt": 18000, "mortgage": 14000, "charitable": 6000, "medical": 0,
                     "other": 0},
        "qbi": {"sstb": False, "w2paid": 0, "ubia": 0}, "rentalActive": False, "household": 4,
        "region": "contig", "acaAddbacks": 0}
    res = run_bpm(source, [{"id": "default", "bpm": inp, "marginals": True}], work)["default"]
    rows = []
    for name, (expected, getter) in DEFAULT_REFERENCE.items():
        got = getter(res)
        rows.append((name, expected, got, abs(got - expected) < TOL))
    bpm_ok = all(r[3] for r in rows)
    earned = res["credits"]["earnedIncome"]
    parts = run_app({"id": "default", "mix": "BPM_PARTS", "status": "MFJ", "state": "CO",
                     "age": 45, "children": 2, "bpm_result": res, "earned_income": earned}, env)
    app_rows = [
        ("Federal ordinary tax (RETpy brackets on BPM's ordinary taxable income)", 19728.53,
         parts["fed_ordinary"]),
        ("LTCG tax (RETpy stacking on BPM's taxable income)", 1050.00, parts["ltcg_tax"]),
        ("CO state tax (RETpy 4.40% on BPM's state base)", 6368.91, parts["state_tax"]),
        ("Child tax credit (RETpy)", 4400.00, parts["ctc"]),
        ("W-2 FICA (RETpy, two earners)", 12775.50, parts["fica"]),
    ]
    app_rows = [(n, e, g, abs(g - e) < TOL) for n, e, g in app_rows]
    return {"bpm_rows": rows, "bpm_ok": bpm_ok, "app_rows": app_rows,
            "app_ok": all(r[3] for r in app_rows), "marginals": res["totals"]["marginals"]}


# ----------------------------------------------------------------------- comparison
# Findings of the first run of this harness that are now fixed (federal ordering). Kept as a
# plain section at the end of the report so a regenerated report still says why those edge
# fixtures are plain "match" rows.
FEDERAL_FIXED_NOTE = [
    "", "## 8. Fixed: income order inside a year (federal and state)", "",
    "The first run found 81 fixtures where the engine's federal tax differed from BPM's and "
    "from RETpy's own tables worked in IRS order. All three causes were engine order bugs, "
    "now fixed: the engine books each event (pension draw, sale of shares, Social Security, "
    "Roth conversion) as the change in one whole-year figure "
    "(`AccountPortfolio._federal_year_tax`).", "",
    "| Cause | Fixtures | Largest gap ($) | Example | Fixed |", "| --- | ---: | ---: | --- | --- |",
    "| Gains were taxed before Social Security was added, so taxable Social Security did not "
    "push gains up the 0/15/20% stack or into NIIT | 78 | 1,674.00 | CA-MFJ-ORD-LTCG-SS | yes |",
    "| Unused standard deduction (ordinary income below it) did not shelter gains | 2 | "
    "4,830.00 | EDGE-ltcg-no-ordinary | yes |",
    "| The senior deduction was not re-priced when later gains raised MAGI | 1 | 396.00 | "
    "EDGE-senior-S-cap-ltcg | yes |", "",
    "After the fix every one of these fixtures matches BPM to the cent. Pinned by "
    "`tests/test_federal_tax_order.py`.", "",
    "State tax follows the same rule: gains sold earlier in the year (after the state's "
    "capital-gains exclusion) are part of the state base for income that comes later, so "
    "the state tax booked does not depend on the order of events. The fixtures book "
    "ordinary income first, so their results are unchanged apart from the Social Security "
    "states (MN MT NM RI VT), where Social Security now sits above the gains in the state "
    "brackets. The federal worksheet's last line (tax no higher than the ordinary tax on all "
    "taxable income) is also applied; BPM leaves it out, and no fixture falls in the "
    "range where it matters (at most $28.50 Single, $57 joint).", "",
]


def money(x):
    return f"{x:,.2f}"


def _finding(bucket, reason, gap, where):
    return {"bucket": bucket, "reason": reason, "gap": abs(gap), "where": where}


ENGINE_GAINS = "account_simulation.py: AccountPortfolio._withdraw_single_pass, _tax_home_sale_gain"
ENGINE_SS = "account_simulation.py: _true_up_social_security_tax, calculate_marginal_tax_on_income"


def compare(fx, app, bpm):
    """Return (metrics, findings): metrics = {name: (app, bpm)}, findings = list of
    {bucket, reason, gap, where} (empty = full match)."""
    m, a, b = {}, app["modeled"], bpm
    neutral = app["neutral"]
    m["fed_ordinary"] = (a["fed_ordinary"], b["federal"]["fedOrdinary"])
    m["ltcg_tax"] = (a["ltcg_tax"], b["federal"]["ltcgTax"])
    m["niit"] = (a["niit"], b["federal"]["niit"])
    m["agi"] = (a["agi"], b["income"]["agi"])
    m["ss_taxable"] = (a["ss_taxable"], b["ss"]["taxable"])
    m["irmaa_tier"] = (float(a["irmaa_tier"]), float(b["irmaa"]["tier"]))
    if fx["mix"] == "W2":
        m["fica"] = (a["fica"], b["payroll"]["w2FICA"] + b["payroll"]["addlMedicare"])
        if fx["state"] == "CA":
            m["sdi"] = (a["sdi"], b["state"]["sdi"])
    m["state_tax"] = (neutral["state_tax"], b["state"]["stateTax"])
    findings = []
    bad = {k for k, (x, y) in m.items() if abs(x - y) >= TOL}
    irs = a.get("irs")
    for k in sorted(bad - {"state_tax"}):
        x, y = m[k]
        gap = x - y
        if k == "fed_ordinary":
            ot = b["income"]["ordinaryTaxable"]
            # BPM's HoH 24% band ends at 201,775, not 201,750: BPM's tax is lower by 8% of
            # the gap, for every income above 201,750.
            offset = 0.08 * (min(ot, 201_775) - 201_750)
            if fx["status"] == "HOH" and ot > 201_750 and abs(gap - offset) < TOL:
                findings.append(_finding(
                    "BPM simplification", "BPM tops the HoH 24% band at 201,775 (statute: "
                    "201,750), so its ordinary tax is up to $2 low above that",
                    gap, "BPM TABLES.federal.hoh; RETpy config.FEDERAL_BRACKETS_BY_STATUS "
                    "is right (Rev. Proc. 2025-32)"))
            elif irs and abs(irs[k] - y) < TOL:
                findings.append(_finding(
                    "RETpy bug", "the senior deduction shrinks as MAGI rises, but ordinary tax "
                    "already booked is not re-priced when later gains or Social Security "
                    "raise MAGI; the same tables in IRS order give BPM's figure", gap,
                    ENGINE_GAINS + "; config.standard_deduction_for_return"))
            else:
                findings.append(_finding("RETpy bug", "fed_ordinary differs (unexplained)",
                                         gap, "unknown"))
        elif k in ("ltcg_tax", "niit") and irs and abs(irs[k] - y) < TOL:
            if fx.get("ss"):
                cause = ("gains are taxed before Social Security is added to income, so taxable "
                         "Social Security does not push gains up the stack or into NIIT")
                where = ENGINE_GAINS + "; " + ENGINE_SS
            elif "senior_order" in fx["tags"]:
                cause = ("the gain's stacking base uses the senior deduction computed before "
                         "the gain raised MAGI")
                where = ENGINE_GAINS
            else:
                cause = ("unused standard deduction does not shelter gains (the stack starts "
                         "at ordinary income minus the deduction, floored at 0)")
                where = ENGINE_GAINS
            findings.append(_finding("RETpy bug", f"{k}: {cause}; the same tables in IRS order "
                                     "give BPM's figure", gap, where))
        elif k == "irmaa_tier" and "irmaa_top" in fx["tags"]:
            findings.append(_finding(
                "BPM simplification", "BPM needs MAGI over the top IRMAA boundary; CMS and "
                "RETpy put the top tier at or above it", gap,
                "BPM TABLES.irmaa; RETpy config.medicare_irmaa_tier"))
        else:
            findings.append(_finding("RETpy bug", f"{k} differs (unexplained)", gap, "unknown"))
    # The state result as RETpy ships it differs from BPM through app-only rules.
    modeled_gap = abs(a["state_tax"] - b["state"]["stateTax"]) >= TOL
    where = f"state_tax_data.STATES['{fx['state']}']"
    if "state_tax" in bad:
        known = STATE_KNOWN.get(fx["state"])
        gap = neutral["state_tax"] - b["state"]["stateTax"]
        if known and (known[2] is None or fx["status"] in known[2]):
            if (known[3] is not None and gap * known[3] < 0) or abs(gap) > known[4]:
                findings.append(_finding(
                    "RETpy bug", f"state_tax: {known[1]}, but the gap has the wrong sign or "
                    "is larger than that cause allows (unexplained)", gap, where))
            else:
                findings.append(_finding(known[0], known[1], gap, where))
        else:
            findings.append(_finding(
                "RETpy bug", "state_tax differs after neutralizing app-only rules "
                "(unexplained)", gap, where))
    elif modeled_gap:
        why = ", ".join(RULE_TEXT[r] for r in app["contrib"]) or "app-only state rules"
        findings.append(_finding("BPM simplification", f"{why}; RETpy wins",
                                 a["state_tax"] - b["state"]["stateTax"], where))
    return m, findings


def bucket_of(findings):
    return max((f["bucket"] for f in findings), key=PRIORITY.get) if findings else "match"


# --------------------------------------------------------------------------- report
def write_report(path, ctx):
    rows, default = ctx["rows"], ctx["default"]
    counts = {}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    lines = ["# Tax cross-check report: RETpy vs BiggerPockets Money tax engine", "",
             f"Generated {ctx['when']} by `tools/tax_crosscheck/crosscheck.py`. Oracle: "
             "BiggerPockets Money Income Tax Projection Calculator v1.11.2 (2026 tax year). "
             f"Fixtures: {len(rows)}. Tolerance: to the cent.", "",
             "Buckets: **RETpy bug** (RETpy is wrong or inconsistent), **BPM simplification** "
             "(BPM does not model something RETpy does; RETpy wins), **modeling difference** "
             "(both are approximations; the choice is documented). Each state result is "
             "compared with RETpy's app-only rules switched off (personal exemptions and "
             "credits, retirement exclusions, capital-gains exclusion, taxed Social "
             "Security except in Utah), so any remaining gap is a table or mechanics gap.", "",
             "## 1. BPM's own default example", "",
             "BPM engine reproduces its verified figures: "
             f"**{'yes' if default['bpm_ok'] else 'NO'}**. "
             "RETpy's tables reproduce the federal, state, credit and payroll parts: "
             f"**{'yes' if default['app_ok'] else 'NO'}**.", "",
             "| Figure | Reference | BPM engine | Match |", "| --- | ---: | ---: | --- |"]
    for n, e, g, ok in default["bpm_rows"]:
        lines.append(f"| {n} | {money(e)} | {money(g)} | {'yes' if ok else 'NO'} |")
    lines += ["", "| RETpy part | Reference | RETpy | Match |", "| --- | ---: | ---: | --- |"]
    for n, e, g, ok in default["app_rows"]:
        lines.append(f"| {n} | {money(e)} | {money(g)} | {'yes' if ok else 'NO'} |")
    lines += ["", "## 2. Summary", "", "| Bucket | Fixtures |", "| --- | ---: |"]
    for b in ("match", "BPM simplification", "modeling difference", "RETpy bug"):
        lines.append(f"| {b} | {counts.get(b, 0)} |")
    unexplained = [r for r in rows if any("unexplained" in f["reason"] for f in r["findings"])]
    lines += ["", f"Unexplained differences: **{len(unexplained)}**.", "",
              f"Expected-gap edge cases that unexpectedly matched: "
              f"**{len(ctx['gap_closed'])}**"
              + (" (" + ", ".join(ctx["gap_closed"]) + ")" if ctx["gap_closed"] else "") + ".", ""]

    def grouped(bucket):
        agg = {}
        for r in rows:
            for f in r["findings"]:
                if f["bucket"] == bucket:
                    agg.setdefault((f["reason"], f["where"] if bucket == "RETpy bug" else ""),
                                   []).append((r, f))
        return agg
    for title, bucket in (("3. RETpy bugs (findings)", "RETpy bug"),
                          ("4. BPM simplifications (RETpy wins)", "BPM simplification"),
                          ("5. Modeling differences", "modeling difference")):
        lines += [f"## {title}", ""]
        agg = grouped(bucket)
        if not agg:
            lines += ["None.", ""]
            continue
        lines += ["| Cause | Responsible | Fixtures | Largest gap ($) | Examples |",
                  "| --- | --- | ---: | ---: | --- |"]
        for (why, where), rs in sorted(agg.items(), key=lambda kv: -len(kv[1])):
            ex = ", ".join(r["id"] for r, _ in rs[:3])
            states = sorted({r["state"] for r, _ in rs if r["group"] == "grid"})
            extra = f" (states: {' '.join(states)})" if 0 < len(states) <= 12 else ""
            where = where or sorted({f["where"] for _, f in rs})[0]
            if bucket != "RETpy bug" and len({f["where"] for _, f in rs}) > 1:
                where = "state_tax_data.STATES rows above"
            gap = max(f["gap"] for _, f in rs)
            lines.append(f"| {why.replace('|', '/')}{extra} | {where.replace('|', '/')} | "
                         f"{len(rs)} | {gap:,.2f} | {ex} |")
        lines.append("")
    lines += ["## 6. Every fixture", "",
              "Each differing figure shows RETpy, then BPM (RETpy minus BPM). `state_tax` is "
              "RETpy with its app-only rules switched off.", "",
              "| Fixture | Scenario | Bucket | Differences |", "| --- | --- | --- | --- |"]
    for r in rows:
        diffs = "; ".join(r["diffs"]) or "none"
        lines.append(f"| {r['id']} | {r['label']} ({r['state']}, {LABEL[r['status']]}) | "
                     f"{r['bucket']} | {diffs} |")
    lines += ["", "## 7. Not compared", "",
              "RETpy models none of these, so they are known gaps rather than findings: the "
              "qualified business income deduction (self-employment income), itemized "
              "deductions and the SALT cap, AMT, the earned income credit, and the ACA "
              "premium-credit cliff (BPM reports only the required-contribution percentage). "
              "BPM does not model them all either (AMT, EITC, loss carryforwards, local "
              "taxes).", ""]
    lines += FEDERAL_FIXED_NOTE
    with open(path, "w") as fh:
        fh.write("\n".join(lines))


# ------------------------------------------------------------------------------ main
def _state_codes():
    with open(os.path.join(REPO, "retirement_sim", "state_tax_data.py")) as fh:
        return re.findall(r'^    "([A-Z]{2})": ', fh.read(), re.M)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bpm-source", default=os.environ.get("BPM_TAX_SOURCE"),
                    help="path to the BPM tax calculator page (calc_tax.html); or set "
                         "BPM_TAX_SOURCE")
    ap.add_argument("--states", default="default",
                    help="default | quick | all | comma list of codes")
    ap.add_argument("--report", default=os.path.join(HERE, "REPORT.md"))
    ap.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 2))
    ap.add_argument("--work-dir", default=None, help="keep intermediate JSON here")
    ap.add_argument("--fail-on", default="unexplained",
                    help="'unexplained' = exit 1 when a difference has no known cause "
                         "(the default); '' = never")
    args = ap.parse_args(argv)
    if not args.bpm_source or not os.path.exists(args.bpm_source):
        ap.error("give --bpm-source (or set BPM_TAX_SOURCE) pointing at the BPM tax calculator "
                 "HTML page")
    if not shutil.which("node"):
        ap.error("node is not on PATH")
    states = {"default": GRID_STATES, "quick": QUICK_STATES, "all": _state_codes()}.get(
        args.states, args.states.split(","))
    work = args.work_dir or tempfile.mkdtemp(prefix="tax_crosscheck_")
    os.makedirs(work, exist_ok=True)
    env = dict(os.environ, RETIREMENT_SIM_PROFILE="/nonexistent/tax-crosscheck-profile.json")

    default = default_example(args.bpm_source, work, env)
    fixtures = build_fixtures(states)
    print(f"{len(fixtures)} fixtures, {args.workers} workers", flush=True)
    apps = run_apps(fixtures, args.workers)
    items = [{"id": fx["id"], "bpm": bpm_input(fx, app["modeled"]["std_extra"])}
             for fx, app in zip(fixtures, apps)]
    bpm = run_bpm(args.bpm_source, items, work)
    with open(os.path.join(work, "app_out.json"), "w") as fh:
        json.dump(apps, fh)

    rows, gap_closed = [], []
    for fx, app in zip(fixtures, apps):
        metrics, findings = compare(fx, app, bpm[fx["id"]])
        diffs = [f"{k} {x:,.2f} vs {y:,.2f} ({x - y:+,.2f})"
                 for k, (x, y) in metrics.items() if abs(x - y) >= TOL]
        if fx["expect"] == "gap" and not findings:
            gap_closed.append(fx["id"])
        rows.append({"id": fx["id"], "label": fx["label"], "state": fx["state"],
                     "status": fx["status"], "group": fx["group"], "diffs": diffs,
                     "findings": findings, "bucket": bucket_of(findings)})
    write_report(args.report, {"rows": rows, "default": default, "gap_closed": gap_closed,
                               "when": datetime.date.today().isoformat()})
    assert "retirement_sim" not in sys.modules, "the driver must never import retirement_sim"
    counts = {}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    print("buckets:", counts, "| default example:", default["bpm_ok"] and default["app_ok"])
    print("report:", args.report)
    fail = [t for t in args.fail_on.split(",") if t]
    unexplained = any("unexplained" in f["reason"] for r in rows for f in r["findings"])
    if not (default["bpm_ok"] and default["app_ok"]):
        return 1
    if "unexplained" in fail and unexplained:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
