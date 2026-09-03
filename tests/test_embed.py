"""The embed script, and where the design width comes from."""

import re

import pytest

from artesian import embed


def test_the_frame_is_never_given_a_percentage_width():
    """
    The iPad bug, encoded so it cannot come back.

    Every browser on an iPad is WebKit underneath, and WebKit sizes an iframe
    to its CONTENT rather than honouring ``width: 100%``. Against a Panel app
    in ``stretch_width`` that is a loop with no fixed point, and the demo runs
    off the side of the page. Both GeomorphOnline exercises shipped with it,
    and no desktop engine shows it -- measured at six widths in Blink and
    three in Gecko, there is no overflow anywhere.

    What is allowed is ``min-width: 100%``, which WebKit does honour.
    """
    assigns = re.findall(r"style\.width\s*=\s*([^;]+);", embed.EMBED_JS)
    assert assigns, "no width assignment found -- has the script changed?"
    for value in assigns:
        assert "'100%'" not in value and '"100%"' not in value, value
    assert "minWidth = '100%'" in embed.EMBED_JS


def test_the_template_is_fully_substituted():
    """A leftover placeholder is a syntax error in the reader's browser, and
    nothing here would otherwise notice."""
    assert "{attribute}" not in embed.EMBED_JS
    assert "{meta}" not in embed.EMBED_JS
    assert embed.EMBED_ATTRIBUTE in embed.EMBED_JS
    assert embed.DESIGN_WIDTH_META in embed.EMBED_JS


def test_write_embed_script_writes_the_script_and_the_stylesheet(tmp_path):
    script, css = embed.write_embed_script(str(tmp_path))
    assert script.endswith(embed.EMBED_FILENAME)
    assert css.endswith(embed.EMBED_CSS_FILENAME)
    assert (tmp_path / embed.EMBED_FILENAME).read_text() == embed.EMBED_JS
    assert (tmp_path / embed.EMBED_CSS_FILENAME).read_text() == embed.EMBED_CSS


def test_write_embed_script_overwrites_older_ones(tmp_path):
    """They are shared by every demo in the directory, so rewriting them on
    each build is what lets one rebuild update them all."""
    (tmp_path / embed.EMBED_FILENAME).write_text("stale")
    (tmp_path / embed.EMBED_CSS_FILENAME).write_text("stale")
    embed.write_embed_script(str(tmp_path))
    assert (tmp_path / embed.EMBED_FILENAME).read_text() == embed.EMBED_JS
    assert (tmp_path / embed.EMBED_CSS_FILENAME).read_text() == embed.EMBED_CSS


def test_the_frame_is_laid_out_before_any_script_runs():
    """
    The regression this stylesheet exists for. The script cannot size a frame
    whose document has not loaded, and a demo pulling tens of megabytes of
    Pyodide leaves that window open for many seconds. Shipped with the sizing
    left entirely to the script, the reader got the browser's default iframe --
    about 300 px wide -- stretched to the page's fallback height: a narrow,
    tall box with blank space beneath, reported as "stuck loading".

    So the static rules have to be in CSS, and they have to be the WebKit-safe
    form, not width: 100%.
    """
    # Strip comments first: the file EXPLAINS why width: 100% is wrong, and a
    # naive search finds that sentence and calls it a violation.
    rules = re.sub(r"/\*.*?\*/", "", embed.EMBED_CSS, flags=re.S)
    assert "min-width: 100%" in rules
    assert "width: 1px" in rules
    assert "width: 100%" not in rules.replace("min-width: 100%", "")
    assert "iframe[%s]" % embed.EMBED_ATTRIBUTE in rules


# ------------------------------------------------------- the design width

def _app(tmp_path, body):
    path = tmp_path / "app.py"
    path.write_text(body)
    return str(path)


def test_the_design_width_is_read_from_the_app(tmp_path):
    """The app declares the width it is laid out for; it needs the number
    anyway, to cap its own layout. Reading it here is what stops the embedding
    page repeating it and the two drifting apart."""
    app = _app(tmp_path, "import panel\nDESIGN_WIDTH = 900\nx = 1\n")
    assert embed.declared_design_width(app) == 900


def test_an_app_without_a_design_width_gets_none(tmp_path):
    app = _app(tmp_path, "x = 1\n")
    assert embed.declared_design_width(app) is None


@pytest.mark.parametrize("body", [
    "DESIGN_WIDTH = compute()\n",          # not a literal
    "DESIGN_WIDTH = 0\n",                  # not a width
    "DESIGN_WIDTH = -900\n",
    "def f():\n    DESIGN_WIDTH = 900\n",  # not module level
])
def test_only_a_positive_module_level_literal_counts(tmp_path, body):
    assert embed.declared_design_width(_app(tmp_path, body)) is None


def test_a_broken_app_does_not_break_the_build(tmp_path):
    """Reading the width is a convenience. If the source will not parse,
    `panel convert` is about to say so far more usefully than a SyntaxError
    raised from here."""
    assert embed.declared_design_width(_app(tmp_path, "def (\n")) is None
    assert embed.declared_design_width(str(tmp_path / "absent.py")) is None


def test_the_width_is_injected_into_the_page_head(tmp_path):
    page = tmp_path / "app.html"
    page.write_text("<html><head>\n<title>x</title>\n</head><body></body></html>")
    assert embed.inject_design_width(str(page), 900) is True
    text = page.read_text()
    assert '<meta name="artesian-design-width" content="900">' in text
    assert text.index("artesian-design-width") < text.index("</head>")


def test_injecting_twice_replaces_rather_than_accumulates(tmp_path):
    """A rebuild must not leave two of them: the script reads the first it
    finds, so a stale one would quietly win."""
    page = tmp_path / "app.html"
    page.write_text("<html><head></head><body></body></html>")
    embed.inject_design_width(str(page), 900)
    embed.inject_design_width(str(page), 1200)
    text = page.read_text()
    assert text.count("artesian-design-width") == 1
    assert 'content="1200"' in text


def test_a_page_with_no_head_is_left_alone(tmp_path):
    page = tmp_path / "app.html"
    page.write_text("<p>not a document</p>")
    assert embed.inject_design_width(str(page), 900) is False
    assert page.read_text() == "<p>not a document</p>"


def test_the_available_width_excludes_the_parents_padding():
    """
    ``clientWidth`` includes padding; the frame lives in the content box. A
    demo scaled to the padded width overflows its column by exactly the
    padding -- invisible in a container that has none, which is how it
    survived two deployments and turned up on a test page with 16 px of it.
    """
    assert "paddingLeft" in embed.EMBED_JS
    assert "paddingRight" in embed.EMBED_JS
    body = embed.EMBED_JS.split("function available_width")[1].split("}")[0]
    assert "clientWidth - pad" in embed.EMBED_JS, body


# -- detecting demos that will never scale --------------------------------

def _page(tmp_path, name, width=None):
    head = '<meta name="artesian-design-width" content="%d">' % width \
        if width else ""
    (tmp_path / name).write_text("<html><head>%s</head><body></body></html>"
                                 % head)
    return tmp_path / name


def test_page_design_width_reads_back_what_was_injected(tmp_path):
    from artesian.embed import inject_design_width, page_design_width
    page = _page(tmp_path, "a.html")
    inject_design_width(str(page), 900)
    assert page_design_width(str(page)) == 900


def test_page_design_width_is_zero_when_absent(tmp_path):
    from artesian.embed import page_design_width
    assert page_design_width(str(_page(tmp_path, "a.html"))) == 0


def test_page_design_width_of_a_missing_file_is_zero(tmp_path):
    from artesian.embed import page_design_width
    assert page_design_width(str(tmp_path / "nope.html")) == 0


def test_unscaled_pages_finds_the_one_without_a_width(tmp_path):
    """The regression this exists for: a shared directory where one demo was
    rebuilt after the width started being recorded and another was not. The
    stale one still loads and still fits its frame -- it just never scales."""
    from artesian.embed import unscaled_pages
    _page(tmp_path, "corestone_panel.html", width=900)
    _page(tmp_path, "grlp_panel.html")
    assert unscaled_pages(str(tmp_path)) == ["grlp_panel.html"]


def test_unscaled_pages_excludes_the_page_just_built(tmp_path):
    from artesian.embed import unscaled_pages
    fresh = _page(tmp_path, "fresh.html")
    assert unscaled_pages(str(tmp_path), exclude=[str(fresh)]) == []


def test_unscaled_pages_ignores_the_generated_index(tmp_path):
    from artesian.embed import unscaled_pages
    _page(tmp_path, "index.html")
    assert unscaled_pages(str(tmp_path)) == []


def test_unscaled_pages_is_quiet_when_all_are_recorded(tmp_path):
    from artesian.embed import unscaled_pages
    _page(tmp_path, "a.html", width=900)
    _page(tmp_path, "b.html", width=700)
    assert unscaled_pages(str(tmp_path)) == []


def test_the_frame_is_re_measured_after_the_app_settles():
    """
    ``adjusting`` suppresses the ResizeObserver callbacks the script's own
    writes cause, and it cannot tell those from a real one arriving in the
    same instant. A render landing in that window is dropped, and the frame
    keeps the height it had while the app was still laying itself out -- blank
    space under the demo, permanently, on a machine fast enough to hit it.

    Reported from a desktop; not reproducible in a headless run, which is slow
    enough that the real render always lands outside the window. So the
    defence is that the measurement is repeated rather than relied on once.
    """
    assert "RETRIES" in embed.EMBED_JS
    assert "setTimeout(fit, RETRIES[i])" in embed.EMBED_JS
    later = re.search(r"var RETRIES = \[([^\]]*)\]", embed.EMBED_JS)
    assert later, "RETRIES list not found"
    delays = [int(x) for x in later.group(1).split(",")]
    assert delays == sorted(delays) and delays[-1] >= 10000, delays


def test_the_observer_follows_the_frames_current_document():
    """
    An iframe does not start empty. It starts with a BLANK document whose
    readyState is already "complete", so a script that looks once attaches its
    ResizeObserver to a body that is about to be discarded, and reads the
    design width from a document with no meta tag in it -- leaving the demo
    unscaled at whatever height the blank document had.

    Reported from Firefox on an iPad, which is WebKit; no desktop engine shows
    it, because there the real document arrives before the script looks.
    """
    assert "observed" in embed.EMBED_JS
    assert "doc === observed" in embed.EMBED_JS
    # fit() must re-check, not just the one-off setup path
    body = embed.EMBED_JS.split("function fit()")[1]
    assert body.lstrip().startswith("{\n      attach();"), body[:120]


def test_the_design_width_is_taken_from_the_element_before_the_document():
    """
    Ordering, and it is the whole point of this function.

    Reading the width out of the compiled page keeps the number in one place,
    but it needs the frame's DOCUMENT to be readable while the page lays
    itself out, and it is not: an iframe starts on a blank document, and on
    WebKit -- every browser on an iPad -- that is what a page script sees. No
    meta, no design width, and the demo is never scaled.

    Both GeomorphOnline exercises worked on an iPad while each page hardcoded
    its design width, and broke in the commit that replaced that with the meta
    tag. So the attribute, which is on the element and readable at once, wins.
    """
    body = embed.EMBED_JS.split("function design_width")[1].split("\n  }")[0]
    attr = body.index("data-design-width")
    meta = body.index("meta[name=")
    assert attr < meta, "the meta tag must be the FALLBACK, not the first look"


def test_the_frame_is_not_scrollable():
    """
    The frame is sized to its content, so it has nothing to scroll. Where it
    can, a touch drag pans the demo off the edge of its own frame and there is
    no obvious way to get it back -- reported on an iPad, where a rounding
    difference of a pixel or two is enough to allow it.

    Belt and braces: the attribute, which some engines only honour before the
    frame loads, and the CSS.
    """
    assert "setAttribute('scrolling', 'no')" in embed.EMBED_JS
    rules = re.sub(r"/\*.*?\*/", "", embed.EMBED_CSS, flags=re.S)
    assert "overflow: hidden" in rules
