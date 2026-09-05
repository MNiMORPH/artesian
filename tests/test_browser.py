"""Load a built demo in a real browser and drive it.

The gap this closes: every serious bug in artesian so far has been invisible
to the rest of the suite, because it lived in the browser rather than in the
build. `panel convert` exiting zero while shipping a stale app; ``width:100%``
sending a demo off the side of an iPad; a periodic callback that disconnected
the controls; wheels stripped on the premise that their JavaScript is never
loaded. The unit tests pass in all four cases. The tool cannot see what it
produces.

Opt-in, because it needs a browser and downloads the Pyodide runtime::

    pip install artesian[browser] && playwright install chromium
    pytest -m browser

It is slow -- roughly 30-60 s -- and hits the network, so it belongs on a
schedule rather than on every push.
"""

import http.server
import re
import socketserver
import threading

import pytest

playwright = pytest.importorskip("playwright.sync_api",
                                 reason="pip install artesian[browser]")
from playwright.sync_api import sync_playwright          # noqa: E402

pytestmark = pytest.mark.browser

HERE = __file__.rsplit("/", 2)[0]
EXAMPLE = HERE + "/examples/hillslope.py"

#: Pyodide downloads tens of megabytes and then boots. Measured at 13-25 s on
#: a loaded workstation; the ceiling is generous so a slow machine reports a
#: real failure rather than a timeout.
BOOT_TIMEOUT_MS = 180_000


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    """A demo compiled from the example, once for the whole session."""
    from artesian import build_app
    out = tmp_path_factory.mktemp("built")
    page = build_app(EXAMPLE, str(out), packages=[HERE],
                     requirements=["numpy"], strip_vendored=True)
    return str(out), page.rsplit("/", 1)[1]


@pytest.fixture
def serve(built):
    """Serve the build over HTTP: file:// breaks the worker's origin rules."""
    directory, page = built

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=directory, **kw)

        def log_message(self, *a):
            pass

    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/%s" % (server.server_address[1], page)
    server.shutdown()


def _largest_canvas(page):
    """Screenshot the plot.

    Through Playwright rather than `document.querySelectorAll`, because panel
    renders into a shadow root: plain DOM queries find no canvas there at all,
    and `toDataURL` comes back empty.
    """
    canvases = page.locator("canvas")
    best, area = None, -1
    for i in range(canvases.count()):
        box = canvases.nth(i).bounding_box()
        if box and box["width"] * box["height"] > area:
            best, area = canvases.nth(i), box["width"] * box["height"]
    return best.screenshot() if best else b""


def test_a_built_demo_boots_renders_and_responds(serve):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("console",
                lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(serve)

        # NOT a wait for markup. `panel convert` embeds a pre-rendered copy of
        # the layout so the page is not blank while Pyodide downloads, so
        # widgets and canvases exist within 0.1 s whether or not anything is
        # running. The app is live only once panel clears `pn-loading`.
        page.wait_for_function(
            "() => document.body"
            " && !document.body.classList.contains('pn-loading')",
            timeout=BOOT_TIMEOUT_MS)

        assert page.locator("canvas").count() > 0, "no plot rendered"
        assert page.locator("button").count() > 0, "no controls rendered"

        # Rendering is not responding: drive it and check the model advances.
        before = _largest_canvas(page)
        page.get_by_role("button",
                         name=re.compile("Run|Play|▶")).first.click()
        page.wait_for_timeout(5000)
        after = _largest_canvas(page)

        assert before, "could not screenshot the plot"
        assert after != before, "the plot did not change after pressing Run"
        assert not errors, "console errors: %s" % errors[:3]

        browser.close()
