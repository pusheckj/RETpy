"""Repro: after a slow scroll through every tile, the What if tile's typed boxes show slider minimums
(0, 40, 0.00) next to sliders at 80, 100, 2.75. Run against the hosted sample (port 8803)."""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).parent))
from vr_common import *
from visual_audit import scroll_pass
from playwright.sync_api import sync_playwright
Q="""()=>[...document.querySelectorAll('.st-key-mc-tile-whatif [class*=st-key-sbx-]')].map(e=>(e.querySelector('[data-testid=stSliderThumbValue]')?.innerText)+'|'+e.querySelector('input')?.value).join('  ')"""
with sync_playwright() as p:
    b=p.webkit.launch()
    pg=b.new_page(viewport={'width':1440,'height':900})
    open_planner(pg); pick_preset(pg); run_sim(pg); expand_all(pg)
    pg.set_viewport_size({'width':1440,'height':1800}); pg.wait_for_timeout(1500)
    scroll_pass(pg)
    print('after scroll pass', pg.evaluate(Q))
    pg.evaluate("document.querySelector('.st-key-mc-tile-whatif').scrollIntoView()")
    for _ in range(30):                      # the lazy tile can take a while on a busy server
        pg.wait_for_timeout(2000)
        if pg.evaluate(Q):
            break
    print('at tile', pg.evaluate(Q))
    b.close()
