#!/usr/bin/env python3
"""Screenshot sidebar sections (tall viewport) for light/dark x desktop/phone. Usage:
python tools/vr_sidebar_shots.py OUT_PREFIX [scenario]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from visual_audit import *   # noqa

prefix = sys.argv[1]
scenario = sys.argv[2] if len(sys.argv) > 2 else "debts"
SECS = ["About you", "Family", "Income", "House", "Expenses", "Debts", "Investments", "Retirement"]
with sync_playwright() as p:
    b = p.webkit.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    scenario_setup(pg, scenario)
    for theme in ("light", "dark"):
        pg.set_viewport_size({"width": 1440, "height": 900}); pg.wait_for_timeout(1000)
        set_theme(pg, theme == "dark"); wait_idle(pg)
        for vp in ("1440", "390"):
            w, h = VIEWPORTS[vp]
            pg.set_viewport_size({"width": w, "height": 2600}); pg.wait_for_timeout(2000)
            for sec in SECS:
                open_sidebar_phone(pg)
                sb = pg.locator('[data-testid="stSidebar"]')
                sb.get_by_text(sec, exact=True).first.click(); pg.wait_for_timeout(1400)
                pg.screenshot(path=f"{prefix}_{theme}_{vp}_{sec.split()[0]}.png", clip={"x": 0, "y": 0, "width": min(w, 460), "height": 2600})
                sb.get_by_text(sec, exact=True).first.click(); pg.wait_for_timeout(500)
            close_sidebar_phone(pg)
            pg.set_viewport_size({"width": 1440, "height": 900}); pg.wait_for_timeout(1500)
    b.close()
