#!/usr/bin/env python3
"""Visual QA harness (not part of pytest): drives the Streamlit app with Playwright webkit,
then audits every tile and sidebar section for overflow, clipped text, overlaps, contrast,
light colours in dark mode, misaligned control rows and control sizes.

  python tools/visual_audit.py --scenario mid --themes light,dark --viewports 1440,1024,390,360 \
      --out /tmp/vr3/audit_mid.json --shots /tmp/vr3/shots_mid

Needs the hosted sample on http://localhost:8803 (RETIREMENT_SIM_HOSTED=1) and `playwright install webkit`.
"""
from __future__ import annotations
import argparse, json, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vr_common import *   # noqa: E402,F401
from playwright.sync_api import sync_playwright   # noqa: E402

JS = (Path(__file__).parent / "vr_audit.js").read_text()
SECTIONS = ["About you", "Family", "Income", "Taxes", "House", "Expenses", "Debts", "Accounts",
            "Investments", "Retirement", "Assumptions"]


def fill(loc, value):
    loc.click()
    loc.fill(str(value))
    loc.press("Enter")


def scenario_setup(pg, scenario):
    open_planner(pg)
    pick_preset(pg)
    sb = pg.locator('[data-testid="stSidebar"]')
    if scenario == "fail":
        sb.get_by_text("Expenses", exact=True).first.click(); pg.wait_for_timeout(1500)
        for label, v in (("Food & groceries ($)", 10000), ("Fun and discretionary ($)", 10000), ("Other ($)", 20000)):
            fill(sb.get_by_label(label, exact=True).first, v); pg.wait_for_timeout(800)
        sb.get_by_text("Expenses", exact=True).first.click(); pg.wait_for_timeout(500)
    if scenario == "debts":
        sb.get_by_text("Debts", exact=True).first.click(); pg.wait_for_timeout(1200)
        data = [("Visa", "Credit card", 12000, 24.99, 300), ("Student loan", None, 28000, 5.5, 320),
                ("Auto loan", None, 18000, 7.25, 410)]
        for i, (name, kind, bal, apr, mn) in enumerate(data):
            pg.get_by_text("Add a debt").click(); pg.wait_for_timeout(2000)
            row = pg.locator(f".st-key-mc-debt-row-{i}")
            fill(row.get_by_label("Balance ($)"), bal); pg.wait_for_timeout(700)
            fill(row.get_by_label("APR (%)"), apr); pg.wait_for_timeout(700)
            fill(row.get_by_label("Minimum ($ a month)"), mn); pg.wait_for_timeout(700)
        fill(sb.get_by_label("Extra each month ($)"), 200); pg.wait_for_timeout(1500)
        sb.get_by_text("Debts", exact=True).first.click(); pg.wait_for_timeout(500)
    run_sim(pg)
    expand_all(pg)


def scroll_pass(pg, dwell=2600):
    """Scroll the whole main area in viewport steps, waiting for each lazy chart to draw."""
    pg.mouse.move(2, 2)
    total = pg.evaluate("document.querySelector('[data-testid=stMain]').scrollHeight")
    step = int(pg.viewport_size["height"] * 0.9)
    y = 0
    while y < total + step:
        pg.evaluate(f"document.querySelector('[data-testid=stMain]').scrollTo(0,{y})")
        pg.wait_for_timeout(dwell)
        y += step
        total = pg.evaluate("document.querySelector('[data-testid=stMain]').scrollHeight")
    pg.evaluate("document.querySelector('[data-testid=stMain]').scrollTo(0,0)")
    pg.wait_for_timeout(800)


def audit(pg, root, dark):
    return pg.evaluate(f"({JS})", {"root": root, "dark": dark})


def open_sidebar_phone(pg):
    btn = pg.locator('[data-testid="stExpandSidebarButton"]')
    if btn.count() and btn.first.is_visible():
        btn.first.click(); pg.wait_for_timeout(1200)


def close_sidebar_phone(pg):
    btn = pg.locator('[data-testid="stSidebarCollapseButton"] button')
    if btn.count() and btn.first.is_visible() and pg.viewport_size["width"] < 900:
        btn.first.click(); pg.wait_for_timeout(800)


def run(args):
    results = {}
    with sync_playwright() as p:
        b = p.webkit.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        scenario_setup(pg, args.scenario)
        for theme in args.themes.split(","):
            pg.set_viewport_size({"width": 1440, "height": 900}); pg.wait_for_timeout(1500)
            set_theme(pg, theme == "dark"); wait_idle(pg)
            for vp in args.viewports.split(","):
                w, h = VIEWPORTS[vp]
                pg.set_viewport_size({"width": w, "height": h}); pg.wait_for_timeout(2500)
                tag = f"{args.scenario}_{theme}_{vp}"
                expand_all(pg)
                pg.set_viewport_size({"width": w, "height": 1800 if w > 600 else 2000}); pg.wait_for_timeout(1500)
                scroll_pass(pg)
                res = {"main": audit(pg, '[data-testid="stMain"]', theme == "dark")}
                if args.shots:
                    scroll_shots(pg, f"{args.shots}_{tag}", dwell=900)
                pg.set_viewport_size({"width": w, "height": h}); pg.wait_for_timeout(1500)
                # sidebar sections, one at a time
                res["sidebar"] = {}
                for sec in SECTIONS:
                    open_sidebar_phone(pg)
                    sb = pg.locator('[data-testid="stSidebar"]')
                    try:
                        sb.get_by_text(sec, exact=True).first.click(timeout=4000)
                    except Exception as e:
                        res["sidebar"][sec] = {"error": str(e)[:80]}; continue
                    pg.wait_for_timeout(1300)
                    res["sidebar"][sec] = audit(pg, '[data-testid="stSidebar"]', theme == "dark")
                    if args.shots and sec in ("Debts", "Investments", "Retirement", "Expenses"):
                        pg.screenshot(path=f"{args.shots}_{tag}_side_{sec.split()[0]}.png")
                    sb.get_by_text(sec, exact=True).first.click(); pg.wait_for_timeout(600)
                close_sidebar_phone(pg)
                results[tag] = res
                print("done", tag, flush=True)
        b.close()
    Path(args.out).write_text(json.dumps(results, indent=1))
    summarize(results)


def summarize(results, limit=12):
    for tag, res in results.items():
        print(f"\n===== {tag}")
        parts = {"main": res["main"], **{f"side:{k}": v for k, v in res["sidebar"].items()}}
        for name, r in parts.items():
            if "error" in r:
                print(f"  [{name}] ERROR {r['error']}"); continue
            dof = r["docOverflow"]
            line = []
            if name == "main" and (dof["doc"] > 0 or dof["main"] > 0 or dof["body"] > 0): line.append(f"DOC-OVERFLOW {dof}")
            for k in ("overflow", "clipped", "overlap", "contrast", "lightbg", "rows", "charts", "boxes"):
                if r[k]: line.append(f"{k}={len(r[k])}")
            print(f"  [{name}] " + (", ".join(line) if line else "clean"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="mid", choices=["mid", "fail", "debts"])
    ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--viewports", default="1440,1024,390,360")
    ap.add_argument("--out", default="/tmp/vr3/audit.json")
    ap.add_argument("--shots", default="")
    run(ap.parse_args())
