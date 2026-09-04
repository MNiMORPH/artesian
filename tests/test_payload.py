"""Reporting what a reader downloads, and making it smaller."""

import os
import zipfile

import pytest

from artesian.payload import (STRIP_MANIFEST, format_payload, payload,
                              pyodide_source, strip_wheel)


def _wheel(tmp_path, name, members):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        for member, body in members.items():
            zf.writestr(member, body)
    return path


def _members(path):
    with zipfile.ZipFile(path) as zf:
        return set(zf.namelist())


# -- stripping ------------------------------------------------------------

def test_removes_source_maps_typescript_and_tests(tmp_path):
    w = _wheel(tmp_path, "panel-1.0-py3-none-any.whl", {
        "panel/dist/a.js": "x" * 100,
        "panel/dist/a.js.map": "m" * 5000,
        "panel/dist/a.ts": "t" * 5000,
        "panel/tests/test_a.py": "T" * 5000,
        "panel-1.0.dist-info/METADATA": "Name: panel",
    })
    before, after, removed = strip_wheel(str(w))

    assert removed == 3
    assert after < before
    assert _members(w) >= {"panel/dist/a.js", "panel-1.0.dist-info/METADATA"}
    assert not [n for n in _members(w) if n.endswith((".map", "a.ts"))]


def test_keeps_type_declarations(tmp_path):
    """.d.ts is a type declaration some tooling reads, and it is small."""
    w = _wheel(tmp_path, "panel-1.0-py3-none-any.whl", {
        "panel/dist/a.d.ts": "d" * 100,
        "panel/dist/a.ts": "t" * 100,
        "panel-1.0.dist-info/METADATA": "Name: panel",
    })
    strip_wheel(str(w))
    assert "panel/dist/a.d.ts" in _members(w)
    assert "panel/dist/a.ts" not in _members(w)


def test_a_wheel_with_nothing_to_remove_is_left_alone(tmp_path):
    """bokeh is this case. A build must not churn a file for no reason."""
    w = _wheel(tmp_path, "bokeh-1.0-py3-none-any.whl", {
        "bokeh/__init__.py": "x" * 100,
        "bokeh-1.0.dist-info/METADATA": "Name: bokeh",
    })
    original = w.read_bytes()
    before, after, removed = strip_wheel(str(w))

    assert removed == 0
    assert before == after
    assert w.read_bytes() == original, "wheel was rewritten needlessly"


def test_the_wheel_says_it_was_modified(tmp_path):
    """The failure to avoid: a filename asserting a provenance the contents
    do not have. The manifest travels inside the wheel, so it cannot be
    separated from the file it describes."""
    w = _wheel(tmp_path, "panel-1.0-py3-none-any.whl", {
        "panel/dist/a.js.map": "m" * 5000,
        "panel-1.0.dist-info/METADATA": "Name: panel",
    })
    strip_wheel(str(w))

    manifest = "panel-1.0.dist-info/%s" % STRIP_MANIFEST
    assert manifest in _members(w)
    with zipfile.ZipFile(w) as zf:
        text = zf.read(manifest).decode()
    assert "NOT the file published on" in text
    assert "source maps" in text


def test_the_stripped_wheel_is_still_a_readable_zip(tmp_path):
    w = _wheel(tmp_path, "panel-1.0-py3-none-any.whl", {
        "panel/__init__.py": "VERSION = 1\n",
        "panel/dist/a.js.map": "m" * 5000,
        "panel-1.0.dist-info/METADATA": "Name: panel",
    })
    strip_wheel(str(w))
    with zipfile.ZipFile(w) as zf:
        assert zf.testzip() is None
        assert zf.read("panel/__init__.py") == b"VERSION = 1\n"


# -- reporting ------------------------------------------------------------

def test_payload_lists_wheels_largest_first(tmp_path):
    (tmp_path / "small-1.0-py3-none-any.whl").write_bytes(b"x" * 10)
    (tmp_path / "big-1.0-py3-none-any.whl").write_bytes(b"x" * 1000)
    names = [name for name, _ in payload(str(tmp_path))]
    assert names[0].startswith("big")


def test_payload_counts_the_app_and_the_embed_assets(tmp_path):
    (tmp_path / "demo.html").write_bytes(b"x" * 10)
    (tmp_path / "demo.js").write_bytes(b"x" * 10)
    (tmp_path / "artesian-embed.js").write_bytes(b"x" * 10)
    names = [n for n, _ in payload(str(tmp_path), app="/somewhere/demo.py")]
    assert set(names) == {"demo.html", "demo.js", "artesian-embed.js"}


def test_payload_ignores_another_apps_page(tmp_path):
    """Demos share a directory; the report is for the one just built."""
    (tmp_path / "demo.html").write_bytes(b"x" * 10)
    (tmp_path / "other.html").write_bytes(b"x" * 10)
    names = [n for n, _ in payload(str(tmp_path), app="demo.py")]
    assert "other.html" not in names


def test_format_reports_decimal_megabytes(tmp_path):
    """Decimal, because that is what a browser's network panel shows."""
    text = format_payload([("w.whl", 1_000_000)])
    assert "1.00 MB" in text


def test_pyodide_source_is_read_from_the_compiled_app(tmp_path):
    (tmp_path / "demo.js").write_text(
        'importScripts("https://cdn.jsdelivr.net/pyodide/v0.29.3/full/pyodide.js");')
    version, url = pyodide_source(str(tmp_path))
    assert version == "v0.29.3"
    assert url.endswith("pyodide.js")


def test_pyodide_source_is_none_when_absent(tmp_path):
    (tmp_path / "demo.js").write_text("nothing here")
    assert pyodide_source(str(tmp_path)) is None


# -- the vendored bundles, and the premise behind removing them -----------

def test_vendored_rules_also_take_the_dist_bundles(tmp_path):
    w = _wheel(tmp_path, "panel-1.0-py3-none-any.whl", {
        "panel/dist/panel.min.js": "j" * 9000,
        "panel/dist/theme.css": "c" * 100,
        "panel/io/resources.py": "p" * 100,
        "panel-1.0.dist-info/METADATA": "Name: panel",
    })
    from artesian.payload import VENDORED_RULES
    strip_wheel(str(w), VENDORED_RULES)
    members = _members(w)

    assert "panel/dist/panel.min.js" not in members
    assert "panel/dist/theme.css" in members, "CSS is not a bundle we serve"
    assert "panel/io/resources.py" in members, "the package's Python must stay"


def test_the_conservative_rules_leave_the_bundles_alone(tmp_path):
    w = _wheel(tmp_path, "panel-1.0-py3-none-any.whl", {
        "panel/dist/panel.min.js": "j" * 9000,
        "panel-1.0.dist-info/METADATA": "Name: panel",
    })
    strip_wheel(str(w))                      # STRIP_RULES by default
    assert "panel/dist/panel.min.js" in _members(w)


def test_premise_holds_when_the_app_loads_its_front_end_from_a_cdn(tmp_path):
    from artesian.payload import wheel_internal_references
    (tmp_path / "demo.html").write_text(
        '<script src="https://cdn.bokeh.org/bokeh/release/bokeh-3.9.2.min.js">')
    assert wheel_internal_references(str(tmp_path)) == []


def test_premise_fails_when_the_app_reaches_into_a_wheel(tmp_path):
    """If this fires, stripping the bundles would remove JavaScript the app
    needs, and a demo that fails in a browser is worse than a large one."""
    from artesian.payload import wheel_internal_references
    (tmp_path / "demo.js").write_text('load("panel/dist/panel.min.js")')
    assert wheel_internal_references(str(tmp_path)) == ["panel/dist/panel.min.js"]


def test_the_embed_script_is_not_mistaken_for_the_app(tmp_path):
    from artesian.payload import wheel_internal_references
    (tmp_path / "artesian-embed.js").write_text('"static/js/whatever.js"')
    assert wheel_internal_references(str(tmp_path)) == []
