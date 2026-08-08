"""`/api/version` answers with or without a watcher.

The page asks for it on every load. When `ent serve` ran without `--watch` the
route did not exist, so every load logged a 404 in the console and the reload
feature failed silently — it looked like a broken surface. The endpoint now
always answers and says whether live reload is actually running.
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jsonschema")

from ent.server import version_payload  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REFUNDLY = REPO_ROOT / "examples" / "refundly"


class _FakeWatcher:
    version = 7


def test_payload_without_a_watcher_tells_the_page_to_stop() -> None:
    assert version_payload(None) == {"version": None, "watching": False}


def test_payload_with_a_watcher_carries_the_version() -> None:
    assert version_payload(_FakeWatcher()) == {"version": 7, "watching": True}


def test_page_stops_polling_when_not_watching() -> None:
    html = (REPO_ROOT / "src/ent/universe.html").read_text()
    assert "watching === false" in html, "the poller must honour watching:false"


def _get(url: str, timeout: float = 5.0) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def test_plain_serve_answers_version_with_200(tmp_path: Path) -> None:
    """The live regression: plain `ent serve` must not 404 this route."""
    port = "7391"
    proc = subprocess.Popen(
        [sys.executable, "-m", "ent.cli", "serve", "--port", port],
        cwd=str(REFUNDLY), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        url = f"http://127.0.0.1:{port}/api/version"
        status, body = 0, ""
        for _ in range(40):                       # wait for bind
            try:
                status, body = _get(url)
                break
            except OSError:
                time.sleep(0.25)
        assert status == 200, f"plain serve returned {status} for /api/version"
        assert '"watching": false' in body.replace(" ", " ").lower() or \
               '"watching":false' in body.lower().replace(" ", "")
    finally:
        proc.terminate()
        proc.wait(timeout=10)
