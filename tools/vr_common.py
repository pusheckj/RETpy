"""Shared Playwright (webkit) helpers for the visual audit. Not part of pytest."""
from __future__ import annotations
import time

HOSTED = "http://localhost:8803"
VIEWPORTS = {"1440": (1440, 900), "1024": (1024, 768), "390": (390, 844), "360": (360, 740)}


def wait_idle(pg, timeout=240):
    t = time.time()
    pg.wait_for_timeout(1500)
    while time.time() - t < timeout:
        txt = pg.inner_text("body")
        if "Running" not in txt and "Simulating" not in txt and "Skip for now" not in txt:
            # stale "Running" check done; make sure the status shows up to date or finished
            break
        pg.wait_for_timeout(2000)
    pg.wait_for_timeout(1500)


def open_planner(pg, url=HOSTED):
    pg.goto(url)
    pg.wait_for_timeout(5000)
    pg.get_by_text("Open the retirement planner").click()
    pg.wait_for_timeout(4000)
    pg.get_by_test_id("stBaseButton-tertiary").first.click()
    wait_idle(pg)


def open_settings(pg):
    pg.get_by_text("Settings", exact=True).first.click()
    pg.wait_for_timeout(1200)


def set_theme(pg, dark: bool):
    open_settings(pg)
    pg.get_by_text("🌙 Dark" if dark else "☀ Light").first.click()
    pg.wait_for_timeout(2500)
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(500)


def pick_preset(pg, name="Mid-career couple"):
    open_settings(pg)
    pop = pg.locator('[data-testid="stPopoverBody"]')
    pop.locator('[data-baseweb="select"]').nth(2).click()
    pg.wait_for_timeout(600)
    pg.get_by_role("option", name=name).first.click()
    pg.wait_for_timeout(1500)
    pg.keyboard.press("Escape")
    wait_idle(pg)


def run_sim(pg):
    pg.get_by_text("Run simulation").first.click()
    pg.mouse.move(2, 2)
    pg.wait_for_timeout(3000)
    wait_idle(pg)


def expand_all(pg):
    try:
        pg.get_by_text("Expand all", exact=True).first.click(timeout=3000)
        pg.wait_for_timeout(2500)
    except Exception:
        pass


def tall_shot(pg, path, w, h=9000):
    """Screenshot the whole scrollable main area by growing the viewport."""
    pg.set_viewport_size({"width": w, "height": h})
    pg.wait_for_timeout(2500)
    pg.screenshot(path=path)


def scroll_shots(pg, prefix, step=None, dwell=700):
    """Scroll the main container and save one viewport screenshot per step."""
    vh = pg.viewport_size["height"]
    step = step or int(vh * 0.92)
    total = pg.evaluate("document.querySelector('[data-testid=stMain]').scrollHeight")
    paths, y, i = [], 0, 0
    while y < total:
        pg.evaluate(f"document.querySelector('[data-testid=stMain]').scrollTo(0,{y})")
        pg.wait_for_timeout(dwell)
        path = f"{prefix}_{i:02d}.png"
        pg.screenshot(path=path)
        paths.append(path)
        y += step
        i += 1
    pg.evaluate("document.querySelector('[data-testid=stMain]').scrollTo(0,0)")
    return paths
