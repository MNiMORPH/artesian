"""URL localization: the step that removes the run-time CDN dependency."""

import os

import pytest

from artesian.build import localize_wheel_urls

CDN = "https://cdn.holoviz.org/panel/1.9.3/dist/wheels/"


def _wheels(tmp_path, *names):
    for name in names:
        (tmp_path / name).write_bytes(b"")


def test_rewrites_cdn_url_to_bare_filename(tmp_path):
    _wheels(tmp_path, "panel-1.9.3-py3-none-any.whl")
    (tmp_path / "app.js").write_text(
        "load('%spanel-1.9.3-py3-none-any.whl')" % CDN)

    assert localize_wheel_urls(str(tmp_path)) == ["app.js"]
    assert (tmp_path / "app.js").read_text() == \
        "load('panel-1.9.3-py3-none-any.whl')"


def test_leaves_urls_without_a_local_wheel_alone(tmp_path):
    """A wheel we did not self-host must keep its absolute URL."""
    _wheels(tmp_path, "panel-1.9.3-py3-none-any.whl")
    url = "https://files.pythonhosted.org/x/scipy-1.2.0-cp39-manylinux.whl"
    (tmp_path / "app.js").write_text("load('%s')" % url)

    assert localize_wheel_urls(str(tmp_path)) == []
    assert url in (tmp_path / "app.js").read_text()


def test_already_local_reference_is_unchanged(tmp_path):
    _wheels(tmp_path, "grlp-3.0.0-py3-none-any.whl")
    (tmp_path / "app.js").write_text("load('grlp-3.0.0-py3-none-any.whl')")

    assert localize_wheel_urls(str(tmp_path)) == []


def test_longer_filename_is_not_shadowed_by_a_shorter_one(tmp_path):
    """`.../extra-panel-1.9.3.whl` must not become `panel-1.9.3.whl`.

    Guarded twice over -- by the `/` path-segment anchor and by longest-first
    ordering -- so this fails only when both are removed. Verified to fail in
    exactly that case; breaking either one alone leaves it passing.
    """
    _wheels(tmp_path, "panel-1.9.3-py3-none-any.whl",
            "extra-panel-1.9.3-py3-none-any.whl")
    (tmp_path / "app.js").write_text(
        "load('%sextra-panel-1.9.3-py3-none-any.whl')" % CDN)

    localize_wheel_urls(str(tmp_path))
    assert (tmp_path / "app.js").read_text() == \
        "load('extra-panel-1.9.3-py3-none-any.whl')"


def test_rewrites_html_and_js_together(tmp_path):
    _wheels(tmp_path, "bokeh-3.9.1-py3-none-any.whl")
    for name in ("app.js", "app.html"):
        (tmp_path / name).write_text("%sbokeh-3.9.1-py3-none-any.whl" % CDN)

    assert sorted(localize_wheel_urls(str(tmp_path))) == ["app.html", "app.js"]


def test_no_wheels_is_a_noop(tmp_path):
    (tmp_path / "app.js").write_text("load('%sx.whl')" % CDN)
    assert localize_wheel_urls(str(tmp_path)) == []


def test_missing_named_file_is_skipped(tmp_path):
    _wheels(tmp_path, "panel-1.9.3-py3-none-any.whl")
    assert localize_wheel_urls(str(tmp_path), ("nonexistent.js",)) == []
