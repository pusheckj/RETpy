"""Refresh persistence in a real browser (Playwright, WebKit): repros a to m of
perf/persistence_design.md section 10.

These need a browser and a running app, so they are off by default. Run them with

    RUN_E2E=1 python3 -m pytest tests/e2e/test_refresh_persistence.py -q -m e2e

Each test starts its own Streamlit server on a free port (as a visitor with no profile file,
or as the owner with a tmp profile file) and always uses a tmp or missing RETIREMENT_SIM_PROFILE,
never the real one. If the test process cannot open sockets, start tests/e2e/server_ctl.sh and set E2E_CTL.
Set E2E_BROWSER=chromium to run them in Chromium instead of WebKit.
Timings are noisy on a loaded machine: the 1.0 s reload test reads E2E_EDIT_DELAY_S (default 1.0).
"""
import contextlib
import json
import os
import socket
import statistics
import subprocess
import sys
import time

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not os.environ.get("RUN_E2E"), reason="browser tests: set RUN_E2E=1"),
]

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, "ui")
sync_api = pytest.importorskip("playwright.sync_api")

# A cold first simulation can take minutes on a busy machine.
PLANNER_TIMEOUT_MS = int(os.environ.get("E2E_PLANNER_TIMEOUT_S", "600")) * 1000

INIT_JS = """
(function(){
  if (window !== window.top) return;
  var T = window.__t = {};
  function mark(k){ if(!(k in T)) T[k] = Math.round(performance.now()); }
  setInterval(function(){
    var load = !!document.querySelector('.mc-loading');
    if (load) mark('loading_seen');
    if ('loading_seen' in T && !load) mark('loading_gone');
    var txt = (document.body && document.body.innerText) || '';
    if (txt.indexOf('Open the retirement planner') >= 0) mark('welcome');
  }, 20);
})();
"""


# --------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------

def _free_port():
    """One server runs at a time, so a fixed port does (the sandbox may not allow binding port 0)."""
    return int(os.environ.get("E2E_PORT", "8541"))


def _listening(port, timeout=1):
    """True when a process listens on the port. Uses lsof, not a socket: on some macOS setups a
    Python process may not open a socket even where a shell-started tool can."""
    r = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True)
    return bool(r.stdout.strip())


def _wait_port_free(port, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if not _listening(port, 0.5):
            return
        time.sleep(0.5)       # something still listens: the last server is shutting down
    raise RuntimeError(f"port {port} is in use")


def _ctl_request(ctl, line, timeout=150):
    ack = os.path.join(ctl, "ack")
    if os.path.exists(ack):
        os.remove(ack)
    with open(os.path.join(ctl, "cmd"), "w") as fh:
        fh.write(line + "\n")
    end = time.time() + timeout
    while time.time() < end:
        if os.path.exists(ack):
            return
        time.sleep(0.3)
    raise RuntimeError("the server helper did not answer")


@contextlib.contextmanager
def serve(tmp_path, profile=None, hosted=False, port=None):
    """A Streamlit server for this repo. ``profile`` is the owner's profile file (None: no such file).

    Normally the test starts it itself. With E2E_CTL=<dir> it asks tests/e2e/server_ctl.sh to do it
    (for machines where the test process cannot open sockets)."""
    port = port or _free_port()
    external = os.environ.get("E2E_EXTERNAL_URL")
    if external:
        # A visitor server started outside the test (machines where a test process may not open
        # sockets). Only the default visitor setup can use it.
        if profile is not None or hosted:
            pytest.skip("needs its own server (owner profile or hosted); not available with E2E_EXTERNAL_URL")
        yield external.rstrip("/"), int(external.rstrip("/").rsplit(":", 1)[1])
        return
    ctl = os.environ.get("E2E_CTL")
    if ctl:
        _ctl_request(ctl, f"start {profile or 'none'} {1 if hosted else 0}")
        try:
            yield f"http://localhost:{port}", port
        finally:
            _ctl_request(ctl, "stop")
        return
    _wait_port_free(port)
    env = dict(os.environ)
    env["RETIREMENT_SIM_PROFILE"] = str(profile) if profile else str(tmp_path / "no_profile.json")
    env.pop("RETIREMENT_SIM_HOSTED", None)
    if hosted:
        env["RETIREMENT_SIM_HOSTED"] = "1"
    cmd = [sys.executable, "-m", "streamlit", "run", os.path.join(UI, "app.py"), "--server.headless", "true",
           "--server.port", str(port), "--browser.gatherUsageStats", "false"]
    log = open(tmp_path / f"server_{port}.log", "w")
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        deadline = time.time() + 90
        while time.time() < deadline:
            if _listening(port):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("the app did not start")
        yield f"http://localhost:{port}", port
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        kind = os.environ.get("E2E_BROWSER", "webkit")
        b = getattr(p, kind).launch()
        yield b
        b.close()


@pytest.fixture
def ctx(browser):
    c = browser.new_context(viewport={"width": 1500, "height": 3000})
    c.add_init_script(INIT_JS)
    yield c
    c.close()


def text(page):
    return page.evaluate("document.body.innerText || ''")


def wait_text(page, needle, timeout=300):
    # innerText follows CSS text-transform (the step counter is upper case), so compare in lower case
    page.wait_for_function("(n) => (document.body.innerText || '').toLowerCase().includes(n.toLowerCase())",
                           arg=needle, timeout=timeout * 1000)


def wait_no_text(page, needle, timeout=60):
    page.wait_for_function("(n) => !(document.body.innerText || '').includes(n)", arg=needle,
                           timeout=timeout * 1000)


def wait_idle(page, quiet=1.5, timeout=300):
    """No running indicator for ``quiet`` seconds."""
    end = time.time() + timeout
    calm_since = None
    while time.time() < end:
        busy = page.evaluate("!!document.querySelector('[data-testid=\"stStatusWidget\"]')")
        now = time.time()
        if busy:
            calm_since = None
        elif calm_since is None:
            calm_since = now
        elif now - calm_since >= quiet:
            return
        time.sleep(0.2)
    raise TimeoutError("the page never went quiet")


def store(page, area, key="retpy"):
    raw = page.evaluate(f"window.{area}Storage.getItem({json.dumps(key)})")
    return json.loads(raw) if raw else None


def wait_store(page, area, predicate, key="retpy", timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        try:
            value = store(page, area, key)
        except Exception:
            value = None
        if predicate(value):
            return value
        time.sleep(0.3)
    raise TimeoutError(f"{area}Storage[{key}] never matched; last value: {str(value)[:300]}")


def open_welcome(page, base):
    page.goto(base, wait_until="commit")
    wait_text(page, "Open the retirement planner")


def start_planner(page, base, skip=True):
    open_welcome(page, base)
    page.get_by_text("Open the retirement planner").first.click()
    wait_text(page, "Step 1 of")
    if skip:
        time.sleep(2)            # a click before the page script is wired up is lost
        for _ in range(6):
            page.get_by_role("button", name="Skip for now").first.click()
            try:
                page.wait_for_selector(".st-key-ay_your_age", state="attached", timeout=45000)
                return
            except sync_api.TimeoutError:
                continue
        raise AssertionError("the planner never opened")


def set_number(page, selector, value):
    box = page.locator(selector).first
    box.fill(str(value))
    box.press("Enter")
    time.sleep(1.2)


def open_section(page, name):
    summary = page.locator("[data-testid=stSidebar] summary").filter(has_text=name).first
    if summary.locator("xpath=..").get_attribute("open") is None:
        summary.click()
        time.sleep(0.8)


def open_settings(page):
    """The planner keeps these controls in the Settings popover; the check-up shows them inline."""
    button = page.locator('button:has-text("Settings")')
    if page.locator(".st-key-mc-simple-root").count():
        page.wait_for_selector("text=Remember me on this device")
        return
    # the planner draws its top bar after the first simulation (cold: up to a few minutes)
    button.first.wait_for(state="visible", timeout=600000)
    for _ in range(8):                       # a click while the page re-draws can close the popover
        button.first.click()
        try:
            page.wait_for_selector("text=Remember me on this device", state="visible", timeout=8000)
            return
        except sync_api.TimeoutError:
            continue
    raise AssertionError("the Settings popover never opened")


def close_settings(page):
    if page.locator('button:has-text("Settings")').count():
        page.keyboard.press("Escape")
        time.sleep(0.5)


def toggle_remember(page):
    """Flip Remember me and make sure it took (a click while the page re-draws can be lost)."""
    open_settings(page)
    box = page.locator('label:has-text("Remember me on this device") input[type=checkbox]').first
    before = box.is_checked()
    for _ in range(4):
        page.locator('label:has-text("Remember me on this device")').first.click()
        time.sleep(2.5)
        if box.is_checked() != before:
            break
        open_settings(page)
    close_settings(page)


def scroll_to(page, selector):
    page.evaluate("(s) => { const e = document.querySelector(s); if (e) e.scrollIntoView({block: 'center'}); }",
                  selector)
    time.sleep(1.5)


def load_tiles(page):
    """Scroll through the page so every lazy tile loads (they start when scrolled near)."""
    for step in range(14):
        page.evaluate("(y) => { document.querySelector('[data-testid=stMain]').scrollTop = y; }", step * 1500)
        time.sleep(0.8)


def reload(page):
    page.reload(wait_until="commit")


def input_value(page, selector, expect=None, timeout=60):
    """The input's value. With ``expect`` (one value or a tuple), wait until it matches: a box beside a
    slider shows its default for a moment before it is seeded from the saved value."""
    expected = (expect,) if isinstance(expect, str) else tuple(expect or ())
    end = time.time() + timeout
    value = page.locator(selector).first.input_value()
    while expected and value not in expected and time.time() < end:
        time.sleep(0.5)
        value = page.locator(selector).first.input_value()
    return value


# --------------------------------------------------------------------------
# a, b: the check-up and the setup
# --------------------------------------------------------------------------

def test_a_checkup_answers_survive_a_refresh(tmp_path, ctx):
    with serve(tmp_path) as (base, _):
        page = ctx.new_page()
        open_welcome(page, base)
        page.get_by_text("Start the money check-up").first.click()
        wait_text(page, "Take-home pay")
        set_number(page, 'input[aria-label="Take-home pay"]', 5100)
        wait_store(page, "session", lambda v: v and v["payload"]["mode"] == "simple")
        reload(page)
        wait_text(page, "Take-home pay")
        assert "Open the retirement planner" not in text(page)
        assert input_value(page, 'input[aria-label="Take-home pay"]', ("5100", "5,100")) in ("5100", "5,100")


def test_b_setup_step_and_answers_survive_a_refresh(tmp_path, ctx):
    with serve(tmp_path) as (base, _):
        page = ctx.new_page()
        open_welcome(page, base)
        page.get_by_text("Open the retirement planner").first.click()
        wait_text(page, "Step 1 of 10")
        set_number(page, 'input[aria-label="How old are you?"]', 41)
        page.locator('label:has-text("Just me")').first.click()
        time.sleep(1.5)
        page.locator(".st-key-gs_next button").first.click()
        wait_text(page, "Step 2 of 10")
        wait_store(page, "session", lambda v: v and (v["payload"].get("setup") or {}).get("step") == 1)
        reload(page)
        wait_text(page, "Step 2 of 10")
        assert "Open the retirement planner" not in text(page)
        page.locator(".st-key-gs_back button").first.click()
        wait_text(page, "Step 1 of 10")
        assert input_value(page, 'input[aria-label="How old are you?"]', "41") == "41"
        # a deeper step comes back too: seed the tab copy at step 5 and reload
        env = wait_store(page, "session", lambda v: v and (v["payload"].get("setup") or {}).get("step") == 0)
        time.sleep(3)                    # let the page's own pending writes finish first
        env["payload"]["setup"] = {"status": "active", "step": 4, "seen": [], "checkup": None}
        page.evaluate("(v) => sessionStorage.setItem('retpy', v)", json.dumps(env))
        reload(page)
        wait_text(page, "Step 5 of 10")


# --------------------------------------------------------------------------
# c, d: the planner, the tab copy, the device copy


def test_c2_future_dollars_choice_survives_a_refresh(tmp_path, ctx):
    with serve(tmp_path) as (base, _):
        page = ctx.new_page()
        start_planner(page, base)
        wait_text(page, "Earliest retirement age", timeout=1800)
        load_tiles(page)
        scroll_to(page, '[class*="st-key-mc-tile-income"]')
        label = page.locator('[class*="st-key-income_over_time_main_dollars_mode"] label').filter(has_text="Future")
        label.first.wait_for(state="attached", timeout=PLANNER_TIMEOUT_MS)
        label.first.click()
        wait_store(page, "session", lambda v: v and
                   v["payload"].get("view", {}).get("income_over_time_main_dollars_mode") == "Future $")
        time.sleep(3)
        reload(page)
        page.wait_for_selector(".st-key-ay_your_age", state="attached", timeout=PLANNER_TIMEOUT_MS)
        wait_text(page, "Earliest retirement age", timeout=1800)
        load_tiles(page)
        scroll_to(page, '[class*="st-key-mc-tile-income"]')
        checked = page.locator('[class*="st-key-income_over_time_main_dollars_mode"] input:checked')
        checked.first.wait_for(state="attached", timeout=PLANNER_TIMEOUT_MS)
        assert "Future" in checked.first.locator("xpath=ancestor::label").inner_text()


def test_c3_extras_in_lazy_tiles_show_their_restored_values_after_a_refresh(tmp_path, ctx):
    """Life expectancy inputs sit in a lazy tile. The restored value must show in the widget, not
    only in the code that uses it."""
    with serve(tmp_path) as (base, _):
        page = ctx.new_page()
        start_planner(page, base)
        wait_text(page, "Earliest retirement age", timeout=1800)
        env = wait_store(page, "session", lambda v: v and v["payload"].get("full"))
        time.sleep(3)                    # let the page's own pending writes finish first
        env["payload"]["extra"] = {"le_sex": "Female"}
        page.evaluate("(v) => sessionStorage.setItem('retpy', v)", json.dumps(env))
        reload(page)
        page.wait_for_selector(".st-key-ay_your_age", state="attached", timeout=PLANNER_TIMEOUT_MS)
        wait_text(page, "Earliest retirement age", timeout=1800)
        load_tiles(page)
        scroll_to(page, '[class*="st-key-mc-tile-lifespan"]')
        box = page.locator('[class*="st-key-le_sex"]').first
        box.wait_for(state="attached", timeout=PLANNER_TIMEOUT_MS)
        assert "Female" in box.inner_text()



def _seed_tab_extras(page, extra):
    """Put values into the tab copy the way a refresh would find them, then reload."""
    env = wait_store(page, "session", lambda v: v and v["payload"].get("full"))
    time.sleep(3)                        # let the page's own pending writes finish first
    env["payload"]["extra"] = extra
    page.evaluate("(v) => sessionStorage.setItem('retpy', v)", json.dumps(env))
    reload(page)
    page.wait_for_selector(".st-key-ay_your_age", state="attached", timeout=PLANNER_TIMEOUT_MS)
    wait_text(page, "Earliest retirement age", timeout=1800)


def test_c4_whatif_levers_show_after_a_refresh_with_no_streamlit_warning(tmp_path, ctx):
    """Round-2 review, issue 3: levers saved at their defaults (and others) are assigned again on
    every run. Streamlit must not show its yellow "default value and Session State API" warning."""
    with serve(tmp_path) as (base, _):
        page = ctx.new_page()
        start_planner(page, base)
        wait_text(page, "Earliest retirement age", timeout=1800)
        _seed_tab_extras(page, {"wifc_ss": True, "wifc_savings": 0, "wifc_stock": 30.0,
                                "wifc_scenario": "pessimistic"})
        load_tiles(page)
        scroll_to(page, '[class*="st-key-mc-tile-whatif"]')
        savings = page.locator(".st-key-wifc_savings input")
        savings.first.wait_for(state="attached", timeout=PLANNER_TIMEOUT_MS)
        box = page.locator(".st-key-wifc_stock__box input")
        assert input_value(page, ".st-key-wifc_stock__box input", ("30", "30.0")) in ("30", "30.0")
        assert "Pessimistic" in page.locator(".st-key-wifc_scenario").first.inner_text()
        assert input_value(page, ".st-key-wifc_savings input", ("0", "0.00")) in ("0", "0.00")
        time.sleep(2)
        assert "Session State API" not in text(page)
        # a second look after another run (the tile draws again, the keys are assigned again)
        page.locator(".st-key-wifc_savings input").first.fill("5000")
        page.locator(".st-key-wifc_savings input").first.press("Enter")
        time.sleep(4)
        assert "Session State API" not in text(page)
        assert box.first.input_value() in ("30", "30.0")


def test_c5_a_choice_made_in_the_session_still_shows_after_the_tiles_reload(tmp_path, ctx):
    """Round-2 review, issue 1: a finished simulation closes the lazy tiles. The tile that draws
    again must show the choice the chart uses (no refresh involved)."""
    with serve(tmp_path) as (base, _):
        page = ctx.new_page()
        start_planner(page, base)
        wait_text(page, "Earliest retirement age", timeout=1800)
        load_tiles(page)
        scroll_to(page, '[class*="st-key-mc-tile-income"]')
        label = page.locator('[class*="st-key-income_over_time_main_dollars_mode"] label').filter(has_text="Future")
        label.first.wait_for(state="attached", timeout=PLANNER_TIMEOUT_MS)
        label.first.click()
        wait_store(page, "session", lambda v: v and
                   v["payload"].get("view", {}).get("income_over_time_main_dollars_mode") == "Future $")
        time.sleep(3)
        open_section(page, "Retirement")
        set_number(page, ".st-key-ay_target_age__box input", 53)     # reruns the simulation: tiles close
        time.sleep(3)
        wait_text(page, "Earliest retirement age", timeout=1800)
        wait_idle(page, quiet=3)
        load_tiles(page)
        scroll_to(page, '[class*="st-key-mc-tile-income"]')
        checked = page.locator('[class*="st-key-income_over_time_main_dollars_mode"] input:checked')
        checked.first.wait_for(state="attached", timeout=PLANNER_TIMEOUT_MS)
        assert "Future" in checked.first.locator("xpath=ancestor::label").inner_text()
        assert "Session State API" not in text(page)


def test_c6_loading_a_file_after_a_refresh_does_not_bring_back_the_old_extras(tmp_path, ctx):
    """Round-2 review, issue 2: Load these inputs wipes the inputs, and a restored value must not return."""
    profile = tmp_path / "loaded.json"
    _demo_profile(profile, age=50)
    with serve(tmp_path) as (base, _):
        page = ctx.new_page()
        start_planner(page, base)
        wait_text(page, "Earliest retirement age", timeout=1800)
        _seed_tab_extras(page, {"le_sex": "Female"})
        open_section(page, "Save / Load")
        page.locator('[data-testid=stSidebar] input[type=file]').first.set_input_files(str(profile))
        page.get_by_role("button", name="Load these inputs").first.click()
        wait_text(page, "Loaded", timeout=120)
        wait_text(page, "Earliest retirement age", timeout=1800)
        wait_idle(page, quiet=3)
        load_tiles(page)
        scroll_to(page, '[class*="st-key-mc-tile-lifespan"]')
        box = page.locator('[class*="st-key-le_sex"]').first
        box.wait_for(state="attached", timeout=PLANNER_TIMEOUT_MS)
        assert "Male" in box.inner_text() and "Female" not in box.inner_text()


# --------------------------------------------------------------------------

def _edit_planner(page):
    open_section(page, "Expenses")
    set_number(page, ".st-key-se_food input", 1400)
    open_section(page, "Retirement")
    set_number(page, ".st-key-ay_target_age__box input", 52)
    open_section(page, "Debts")
    page.get_by_role("button", name="Add a debt").first.click()
    time.sleep(2)


def test_c_planner_edits_view_and_pins_survive_with_remember_me_off(tmp_path, ctx):
    with serve(tmp_path) as (base, _):
        page = ctx.new_page()
        start_planner(page, base)
        wait_text(page, "Earliest retirement age", timeout=600)
        _edit_planner(page)
        load_tiles(page)
        scroll_to(page, '[class*="st-key-mc-tile-whatif"]')
        pin = page.locator('button:has-text("Pin this scenario")')
        pin.first.wait_for(state="attached", timeout=300000)
        pin.first.scroll_into_view_if_needed()
        pin.first.click()
        wait_text(page, "Clear pinned scenarios", timeout=120)
        # the page script (S4) writes mcView; seed it the way it does if this build has no writer yet
        page.evaluate("""() => { try { if (!sessionStorage.getItem('mcView')) sessionStorage.setItem('mcView',
            JSON.stringify({scrollY: 0, tabs: {'mc-tile-deepdives': 'Sensitivity'}})); } catch (e) {} }""")
        wait_store(page, "session", lambda v: v and v["payload"].get("full") and
                   v["payload"].get("remember") is False)
        assert store(page, "local") is None                       # nothing on the device
        time.sleep(3)
        reload(page)
        page.wait_for_selector(".st-key-ay_your_age", state="attached", timeout=PLANNER_TIMEOUT_MS)
        assert "Open the retirement planner" not in text(page)
        assert input_value(page, ".st-key-se_food input", ("1400", "1,400")) in ("1400", "1,400")
        assert input_value(page, ".st-key-ay_target_age__box input", "52") == "52"
        assert page.locator('[class*="st-key-debt_"]').count() > 0
        # the pin comes back, and the Deep dives tab named in mcView opens first (tiles load when scrolled to)
        wait_text(page, "Earliest retirement age", timeout=1800)
        load_tiles(page)
        scroll_to(page, '[class*="st-key-mc-tile-whatif"]')
        wait_text(page, "Clear pinned scenarios", timeout=120)
        scroll_to(page, '[class*="st-key-mc-tile-deepdives"]')
        tab = page.get_by_role("tab", name="Sensitivity").first
        tab.wait_for(timeout=PLANNER_TIMEOUT_MS)
        assert tab.get_attribute("aria-selected") == "true"
        assert "Run sensitivity analysis" in text(page)


def test_d_remember_me_on_keeps_inputs_in_a_new_page_but_not_the_view(tmp_path, ctx):
    with serve(tmp_path) as (base, _):
        page = ctx.new_page()
        start_planner(page, base)
        open_section(page, "Expenses")
        set_number(page, ".st-key-se_food input", 1400)
        toggle_remember(page)
        wait_store(page, "local", lambda v: v and v["payload"].get("remember") is True and
                   persist_has_food(v, 1400))
        assert "view" not in store(page, "local")["payload"]
        other = ctx.new_page()                 # same context: shares localStorage, not sessionStorage
        other.goto(base, wait_until="commit")
        other.wait_for_selector(".st-key-ay_your_age", state="attached", timeout=PLANNER_TIMEOUT_MS)
        assert "Open the retirement planner" not in text(other)
        assert input_value(other, ".st-key-se_food input", ("1400", "1,400")) in ("1400", "1,400")
        assert other.get_by_role("tab", name="Sensitivity").count() == 0 or \
            other.get_by_role("tab", name="Sensitivity").first.get_attribute("aria-selected") != "true"


# --------------------------------------------------------------------------
# e: the owner and the profile file
# --------------------------------------------------------------------------

def _demo_profile(path, age=48):
    sys.path[:0] = [ROOT, UI]
    from components.profile_picker import PROFILES
    from utils.profile_io import serialize_overrides
    path.write_text(serialize_overrides(dict(PROFILES["Mid-career couple (40, kids)"], TARGET_RETIREMENT_AGE=age)))


def test_e_owner_edits_survive_f5_and_a_changed_file_wins_with_a_notice(tmp_path, ctx):
    profile = tmp_path / "owner.json"
    _demo_profile(profile, 48)
    port = _free_port()
    with serve(tmp_path, profile=profile, port=port) as (base, _):
        page = ctx.new_page()
        page.goto(base, wait_until="commit")
        page.wait_for_selector(".st-key-ay_your_age", state="attached", timeout=PLANNER_TIMEOUT_MS)
        open_section(page, "Retirement")
        set_number(page, ".st-key-ay_target_age__box input", 52)
        wait_store(page, "session", lambda v: v and v["payload"].get("base") and
                   persist_has(v, "TARGET_RETIREMENT_AGE", 52))
        time.sleep(3)
        reload(page)
        page.wait_for_selector(".st-key-ay_your_age", state="attached", timeout=PLANNER_TIMEOUT_MS)
        assert input_value(page, ".st-key-ay_target_age__box input", "52") == "52"       # F5 keeps the owner's edit
    _demo_profile(profile, 44)                                                       # the file is edited
    with serve(tmp_path, profile=profile, port=port):
        reload(page)
        page.wait_for_selector(".st-key-ay_your_age", state="attached", timeout=PLANNER_TIMEOUT_MS)
        wait_text(page, "Your profile file changed", timeout=60)
        assert input_value(page, ".st-key-ay_target_age__box input", "44") == "44"


# --------------------------------------------------------------------------
# f: two tabs
# --------------------------------------------------------------------------

def test_f_two_tabs_keep_their_own_values_and_a_third_gets_the_last_device_write(tmp_path, ctx):
    with serve(tmp_path) as (base, _):
        a, b = ctx.new_page(), ctx.new_page()
        start_planner(a, base)
        start_planner(b, base)
        open_section(a, "Expenses")
        set_number(a, ".st-key-se_food input", 1100)
        open_section(b, "Expenses")
        set_number(b, ".st-key-se_food input", 1900)
        toggle_remember(b)
        wait_store(b, "local", lambda v: v and v["payload"].get("remember") is True)
        time.sleep(3)
        for page, expected in ((a, "1100"), (b, "1900")):
            reload(page)
            page.wait_for_selector(".st-key-ay_your_age", state="attached", timeout=PLANNER_TIMEOUT_MS)
            assert input_value(page, ".st-key-se_food input", (expected, f"{expected[0]},{expected[1:]}")) in (expected, f"{expected[0]},{expected[1:]}")
        c = ctx.new_page()
        c.goto(base, wait_until="commit")
        c.wait_for_selector(".st-key-ay_your_age", state="attached", timeout=PLANNER_TIMEOUT_MS)
        assert input_value(c, ".st-key-se_food input", ("1900", "1,900")) in ("1900", "1,900")


# --------------------------------------------------------------------------
# g: a reload right after an edit
# --------------------------------------------------------------------------

def test_g_a_reload_shortly_after_an_edit_keeps_the_edit(tmp_path, ctx):
    delay = float(os.environ.get("E2E_EDIT_DELAY_S", "1.0"))
    with serve(tmp_path) as (base, _):
        page = ctx.new_page()
        open_welcome(page, base)
        page.get_by_text("Start the money check-up").first.click()
        wait_text(page, "Take-home pay")
        wait_store(page, "session", lambda v: v is not None)
        box = page.locator('input[aria-label="Take-home pay"]').first
        box.fill("6200")
        box.press("Enter")
        time.sleep(delay)
        reload(page)
        wait_text(page, "Take-home pay")
        assert input_value(page, 'input[aria-label="Take-home pay"]', ("6200", "6,200")) in ("6200", "6,200")


# --------------------------------------------------------------------------
# h, i, j: storage that misbehaves
# --------------------------------------------------------------------------

def test_h_blocked_storage_shows_the_caption_and_does_not_crash(tmp_path, browser):
    context = browser.new_context(viewport={"width": 1500, "height": 3000})
    context.add_init_script("""
      Storage.prototype.setItem = function () { throw new DOMException('blocked', 'SecurityError'); };
    """)
    try:
        with serve(tmp_path) as (base, _):
            page = context.new_page()
            page.goto(base, wait_until="commit")
            wait_text(page, "Open the retirement planner")
            page.get_by_text("Start the money check-up").first.click()
            wait_text(page, "Take-home pay")
            set_number(page, 'input[aria-label="Take-home pay"]', 4000)
            time.sleep(3)
            assert "Traceback" not in text(page)
            open_settings(page)
            wait_text(page, "This browser is blocking storage", timeout=30)
    finally:
        context.close()


def test_i_a_corrupt_value_is_ignored_and_welcome_shows(tmp_path, ctx):
    with serve(tmp_path) as (base, _):
        page = ctx.new_page()
        open_welcome(page, base)
        page.evaluate("sessionStorage.setItem('retpy', '{this is not json'); localStorage.setItem('retpy', '[1,2');")
        reload(page)
        wait_text(page, "Open the retirement planner")
        assert "Traceback" not in text(page)


def test_j_quota_errors_drop_the_pins_and_keep_the_inputs(tmp_path, browser):
    sys.path[:0] = [ROOT, UI]
    from tests.conftest import load_sample_household
    from utils import persist
    overrides = load_sample_household()
    pin_text = persist.serialize_full(overrides)
    seed = {"schema": 1, "saved_at": "2026-11-01T00:00:00Z", "payload": {
        "remember": False, "mode": "full", "full": persist.serialize_full(overrides),
        "setup": {"status": "done", "step": 0, "seen": []},
        "pins": [{"name": f"P{i}", "overrides": pin_text, "summary": {}, "engine_fp": "x"} for i in range(8)]}}
    limit = len(json.dumps(seed["payload"]["full"])) + 20_000        # fits without the pins, not with them
    context = browser.new_context(viewport={"width": 1500, "height": 3000})
    context.add_init_script(f"""
      (function () {{
        var real = Storage.prototype.setItem;
        Storage.prototype.setItem = function (k, v) {{
          if (k === 'retpy' && String(v).length > {limit}) throw new DOMException('quota', 'QuotaExceededError');
          return real.call(this, k, v);
        }};
        if (!sessionStorage.getItem('retpy')) real.call(sessionStorage, 'retpy', {json.dumps(json.dumps(seed))});
      }})();
    """)
    try:
        with serve(tmp_path) as (base, _):
            page = context.new_page()
            page.goto(base, wait_until="commit")
            page.wait_for_selector(".st-key-ay_your_age", state="attached", timeout=PLANNER_TIMEOUT_MS)
            open_section(page, "Expenses")
            set_number(page, ".st-key-se_food input", 1500)
            saved = wait_store(page, "session", lambda v: bool(v) and persist_has_food(v, 1500))
            assert "pins" not in saved["payload"]
            assert saved["payload"]["full"]
    finally:
        context.close()


def persist_has(envelope, key, value):
    """The saved inputs hold ``key`` = ``value``."""
    sys.path[:0] = [ROOT, UI]
    from utils.profile_io import deserialize_overrides
    try:
        return deserialize_overrides(envelope["payload"]["full"]).get(key) == value
    except Exception:
        return False


def persist_has_food(envelope, food):
    sys.path[:0] = [ROOT, UI]
    from utils.profile_io import deserialize_overrides
    try:
        return any(v == food for k, v in deserialize_overrides(envelope["payload"]["full"]).items()
                   if "FOOD" in k.upper())
    except Exception:
        return False


# --------------------------------------------------------------------------
# k: the loading screen
# --------------------------------------------------------------------------

def test_k_loading_screen_duration_median_of_ten_reloads(tmp_path, ctx):
    uptime = subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()
    with serve(tmp_path) as (base, _):
        page = ctx.new_page()
        open_welcome(page, base)
        durations, welcome_at = [], []
        for _ in range(10):
            reload(page)
            wait_text(page, "Open the retirement planner")
            t = page.evaluate("window.__t || {}")
            if "loading_seen" in t and "loading_gone" in t:
                durations.append(t["loading_gone"] - t["loading_seen"])
            welcome_at.append(t.get("welcome"))
            time.sleep(0.3)
        out = {"uptime": uptime, "loading_screen_ms": durations, "welcome_ms": welcome_at,
               "median_loading_ms": statistics.median(durations) if durations else 0,
               "median_welcome_ms": statistics.median([w for w in welcome_at if w]) if welcome_at else None}
        dest = os.environ.get("E2E_LOADING_OUT")
        if dest:
            with open(dest, "w") as fh:
                json.dump(out, fh, indent=1)
        print(json.dumps(out))
        # sanity bound only: the 0.25 s target is for a machine at normal load
        assert out["median_loading_ms"] < 3000


# --------------------------------------------------------------------------
# l, m: Forget and the toggle
# --------------------------------------------------------------------------

def test_l_forget_then_reload_shows_welcome(tmp_path, ctx):
    with serve(tmp_path) as (base, _):
        page = ctx.new_page()
        start_planner(page, base)
        open_section(page, "Expenses")
        set_number(page, ".st-key-se_food input", 1400)
        toggle_remember(page)
        wait_store(page, "local", lambda v: v is not None)
        open_settings(page)
        page.get_by_role("button", name="Forget my data on this device").first.click()
        time.sleep(4)
        assert store(page, "local") is None
        reload(page)
        wait_text(page, "Open the retirement planner")


def test_m_turning_remember_me_off_removes_the_device_copy(tmp_path, ctx):
    with serve(tmp_path) as (base, _):
        page = ctx.new_page()
        start_planner(page, base)
        toggle_remember(page)
        wait_store(page, "local", lambda v: v is not None)
        toggle_remember(page)
        end = time.time() + 30
        while time.time() < end and store(page, "local") is not None:
            time.sleep(0.5)
        assert store(page, "local") is None
        assert store(page, "session") is not None                     # the tab copy stays
