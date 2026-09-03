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


def test_write_embed_script_writes_the_script(tmp_path):
    path = embed.write_embed_script(str(tmp_path))
    assert path.endswith(embed.EMBED_FILENAME)
    assert (tmp_path / embed.EMBED_FILENAME).read_text() == embed.EMBED_JS


def test_write_embed_script_overwrites_an_older_one(tmp_path):
    """It is shared by every demo in the directory, so rewriting it on each
    build is what lets one rebuild update them all."""
    (tmp_path / embed.EMBED_FILENAME).write_text("stale")
    embed.write_embed_script(str(tmp_path))
    assert (tmp_path / embed.EMBED_FILENAME).read_text() == embed.EMBED_JS


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
