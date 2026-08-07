"""v6 4.1 — the Universe driven by a real browser (Playwright + Chromium).

NOT collected by default `pytest -q` (the filename has no `test_` prefix, so
the default `test_*.py` glob skips it). Run explicitly:

    pytest tests/frontend/frontend_universe.py -q

Requires the `playwright` package and a Chromium install (CI's optional
`frontend` job gates on browser presence; locally `PLAYWRIGHT_BROWSERS_PATH`
or a default install both work).

The suite serves a scratch copy of examples/refundly through the REAL
`ent serve --watch` stack — CSRF token, live reload, drift fallback and all —
and drives it exactly as an operator would.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")
playwright_sync = pytest.importorskip("playwright.sync_api")

REPO_ROOT = Path(__file__).resolve().parents[2]
REFUNDLY = REPO_ROOT / "examples" / "refundly"

# A pinned Chromium (e.g. /opt/pw-browsers/chromium) wins over Playwright's own
# download when present — pass it as executable_path so a version-skewed
# `playwright` package still launches. Absent → default resolution.
_PINNED_CHROMIUM = next((p for p in (Path("/opt/pw-browsers/chromium"),)
                         if p.exists()), None)


def _launch(pw):
    if _PINNED_CHROMIUM:
        return pw.chromium.launch(executable_path=str(_PINNED_CHROMIUM))
    return pw.chromium.launch()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.15)
    raise TimeoutError(f"server on :{port} never came up")


def _spawn_server(root: Path, port: int) -> subprocess.Popen:
    code = (f"from pathlib import Path\nfrom ent.server import serve\n"
            f"serve(Path({str(root)!r}), port={port}, watch=True)")
    proc = subprocess.Popen([sys.executable, "-c", code],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _wait_port(port)
    return proc


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    root = tmp_path_factory.mktemp("frontend") / "refundly"
    shutil.copytree(REFUNDLY, root)
    port = _free_port()
    proc = _spawn_server(root, port)
    with playwright_sync.sync_playwright() as pw:
        browser = _launch(pw)
        yield type("Env", (), {"root": root, "url": f"http://127.0.0.1:{port}",
                               "browser": browser})
        browser.close()
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture()
def page(env):
    p = env.browser.new_page()
    p.goto(env.url)
    p.wait_for_selector("#summary:not(:empty)", timeout=10_000)
    yield p
    p.close()


# --------------------------------------------------------------------------- #
# the map
# --------------------------------------------------------------------------- #

def test_page_loads_and_shows_the_summary(page) -> None:
    assert "units" in page.text_content("#summary")
    assert page.is_visible("#universe")
    # live mode — the static-snapshot note is hidden
    assert not page.is_visible("#snapshot-note")


def test_canvas_fills_the_viewport(page) -> None:
    # canvas is a replaced element — a bare inset:0 leaves it at its intrinsic
    # 300x150 and the map renders as a corner stamp (regression guard).
    size = page.evaluate("""(() => { const c = document.getElementById('universe');
        return [c.clientWidth, c.clientHeight, innerWidth, innerHeight]; })()""")
    assert size[0] == size[2] and size[1] == size[3], f"canvas {size[:2]} != viewport {size[2:]}"
    # ...and the camera actually framed the graph (fit ran against real dims)
    scale = page.evaluate("cam.scale")
    assert scale > 0.3, f"boot fit collapsed to minimum zoom (scale={scale})"


def test_all_six_lenses_change_the_legend(page) -> None:
    legends = {}
    for lens in ["structure", "flow", "trace", "health", "timeline", "blast"]:
        page.click(f'.lens[data-lens="{lens}"]')
        page.wait_for_timeout(120)
        legends[lens] = page.inner_html("#legend")
        active = page.get_attribute(f'.lens[data-lens="{lens}"]', "class")
        assert "active" in active
    assert len(set(legends.values())) == 6          # every lens has its own legend


def test_selecting_a_unit_opens_its_dossier(page) -> None:
    page.evaluate("select('refundly.decide')")
    page.wait_for_selector("#dossier", state="visible", timeout=5_000)
    body = page.text_content("#dossier-body")
    assert "refundly.decide" in body or "Refund Decider" in body


def test_keyboard_tab_and_enter_select_a_unit(page) -> None:
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    focused = page.evaluate("focusIdx")
    assert focused >= 0


def test_trace_playback_advances(page) -> None:
    page.click('.lens[data-lens="trace"]')
    page.wait_for_selector(".trace-row", timeout=5_000)
    page.click(".trace-row")
    page.wait_for_timeout(100)
    start = page.evaluate("[playing, playHop, playPhase]")
    page.wait_for_timeout(1_200)
    end = page.evaluate("[playing, playHop, playPhase]")
    assert start[0] is True                          # playback started
    assert end[1] > start[1] or end[2] > start[2] or end[0] is False  # …and moved


def test_timeline_scrub_moves_the_playhead(page) -> None:
    page.click('.lens[data-lens="timeline"]')
    page.wait_for_selector("#scrub", timeout=5_000)
    assert page.evaluate("scrubIdx") == -1           # live
    page.eval_on_selector("#scrub", "el => { el.value = 0; el.dispatchEvent(new Event('input')); }")
    page.wait_for_timeout(100)
    assert page.evaluate("scrubIdx") == 0            # scrubbed to the first commit


# --------------------------------------------------------------------------- #
# the control loop (CSRF-protected POSTs, end to end)
# --------------------------------------------------------------------------- #

def test_steer_roundtrip_lands_on_the_file_queue(env, page) -> None:
    page.evaluate("select('refundly.gateway')")
    page.wait_for_selector("#instr", timeout=5_000)
    page.fill("#instr", "clamp refunds to the order amount")
    page.click("#steerBtn")
    queue = env.root / "entiendo" / "steering" / "queue.jsonl"
    deadline = time.time() + 5
    while time.time() < deadline and not queue.exists():
        time.sleep(0.1)
    assert queue.exists(), "steer POST never reached the queue (CSRF or routing broke)"
    rows = [json.loads(l) for l in queue.read_text().splitlines() if l.strip()]
    assert any(r["unit"] == "refundly.gateway"
               and "clamp" in r["instruction"] for r in rows)


def test_post_without_csrf_token_is_403(env, page) -> None:
    status = page.evaluate(
        """async () => {
             const r = await fetch('/api/steer', {method:'POST',
               headers:{'Content-Type':'application/json'},
               body: JSON.stringify({unit:'refundly.gateway', instruction:'x'})});
             return r.status;
           }""")
    assert status == 403                             # header missing → rejected


def test_approve_applies_a_seeded_proposal(env) -> None:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from ent import steering
    target = env.root / "src" / "orders" / "store.py"
    before = target.read_text()
    after = before + "\n# approved-live\n"
    steering.propose_from_outcome(env.root, "steer-frontend-1", {
        "unit": "refundly.orders",
        "diffs": {"src/orders/store.py": {"before": before, "after": after}},
        "unifiedDiffs": {"src/orders/store.py": "+# approved-live"}})
    page = env.browser.new_page()
    try:
        page.goto(env.url)
        page.wait_for_selector("#summary:not(:empty)", timeout=10_000)
        # proposals live in the gated unit's dossier — open it first
        page.evaluate("select('refundly.orders')")
        # exact button match — a bare text= would substring-match the diff body
        page.wait_for_selector("#proposals button.act.primary", timeout=5_000)
        page.click("#proposals button.act.primary")
        deadline = time.time() + 5
        while time.time() < deadline and "approved-live" not in target.read_text():
            time.sleep(0.1)
        assert "approved-live" in target.read_text()
    finally:
        page.close()


# --------------------------------------------------------------------------- #
# live reload + drift fallback + the empty Universe
# --------------------------------------------------------------------------- #

def test_broken_manifest_serves_last_good_view_with_drift_banner(env) -> None:
    manifest = env.root / "src" / "gateway" / "entiendo.node.yaml"
    good = manifest.read_text()
    page = env.browser.new_page()
    try:
        page.goto(env.url)
        page.wait_for_selector("#summary:not(:empty)", timeout=10_000)
        manifest.write_text("id: [broken\n")         # half-typed edit
        # the watcher bumps /api/version → the page reloads itself → the graph
        # request fails → last good view + banner
        page.wait_for_selector("#drift-banner", state="visible", timeout=15_000)
        assert "stale" in page.text_content("#drift-banner")
        assert "units" in page.text_content("#summary")   # last good view, not blank
    finally:
        manifest.write_text(good)                    # heal the tree for later tests
        page.close()


def test_empty_repo_invites_ent_init(env, tmp_path) -> None:
    port = _free_port()
    proc = _spawn_server(tmp_path, port)          # a second server, empty root
    page = env.browser.new_page()                 # reuse the module browser
    try:
        page.goto(f"http://127.0.0.1:{port}")
        page.wait_for_selector("#empty", state="visible", timeout=10_000)
        assert "ent init" in page.text_content("#empty")
    finally:
        page.close()
        proc.terminate()
        proc.wait(timeout=10)


def test_windows_open_drag_and_tab(env, page) -> None:
    # v7: three windows at once — the thing a detail pane structurally cannot do
    for uid in ("refundly.decide", "refundly.gateway", "refundly.parse_email"):
        page.evaluate(f"openWindow('{uid}')")
    page.wait_for_timeout(300)
    assert page.evaluate("[...wins.values()].filter(w=>!w.minimized).length") == 3
    win = page.locator('.win[data-unit="refundly.decide"]')
    page.evaluate("focusWin('refundly.decide')")     # raise above the cascade
    # tabs switch and populate from the payload — zero network requests
    win.locator('.wtabs button[data-tab="evals"]').click()
    assert "tier0" in win.locator(".wbody").text_content()
    win.locator('.wtabs button[data-tab="contract"]').click()
    body = win.locator(".wbody").text_content()
    assert "verified" in body or "unverified" in body
    # drag by header moves it
    before = page.evaluate("document.querySelector('.win[data-unit=\"refundly.decide\"]').offsetLeft")
    box = win.locator("header").bounding_box()
    page.mouse.move(box["x"] + 60, box["y"] + 12)
    page.mouse.down(); page.mouse.move(box["x"] + 260, box["y"] + 160, steps=4); page.mouse.up()
    after = page.evaluate("document.querySelector('.win[data-unit=\"refundly.decide\"]').offsetLeft")
    assert after != before
    page.evaluate("[...wins.keys()].forEach(id=>closeWin(id))")
