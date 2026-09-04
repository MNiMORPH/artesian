"""build_app() argument handling and its silent-failure guard."""

import os
import warnings

import pytest

from artesian import build as build_mod
from artesian.build import build_app


def test_rejects_unknown_mode(tmp_path):
    app = tmp_path / "a.py"
    app.write_text("DESIGN_WIDTH = 900\n")
    with pytest.raises(ValueError, match="mode must be one of"):
        build_app(str(app), str(tmp_path / "out"), mode="webassembly")


def test_missing_app_is_reported_before_any_work(tmp_path):
    with pytest.raises(FileNotFoundError, match="Panel app not found"):
        build_app(str(tmp_path / "nope.py"), str(tmp_path / "out"))


def test_raises_when_convert_produces_no_page(tmp_path, monkeypatch):
    """`panel convert` can print a failure and still exit 0; a build that
    wrote nothing must not be reported as success."""
    app = tmp_path / "a.py"
    app.write_text("DESIGN_WIDTH = 900\n")
    monkeypatch.setattr(build_mod, "_run", lambda *a, **k: None)

    with pytest.raises(RuntimeError) as exc:
        build_app(str(app), str(tmp_path / "out"), self_host=())
    message = str(exc.value)
    assert "did not produce" in message
    assert "importable here" in message      # names the actual cause


def test_a_refused_conversion_does_not_pass_off_a_previous_build(tmp_path,
                                                                monkeypatch):
    """Existence is not freshness.

    Every exercise on a site shares one output directory, so rebuilding into a
    directory that already holds a build is the normal case rather than the
    exception. `panel convert` reports some failures on stdout and still exits
    0; when it refuses an app, the earlier page is still sitting there. Checking
    only that the page exists therefore reported success and shipped the OLD
    app under the new one's name -- and because `localize_wheel_urls` runs next
    and rewrites that page, even its timestamp looked fresh afterwards.

    Observed in the wild on 2026-09-04: a hillslope demo whose app raised
    AttributeError at import built "successfully" three times, and the stale
    build was caught only by grepping the emitted .js for a line that had been
    changed.
    """
    app = tmp_path / "a.py"
    app.write_text("DESIGN_WIDTH = 900\n")
    out = tmp_path / "out"
    out.mkdir()
    stale = out / "a.html"
    stale.write_text("<html>the previous build</html>")
    before = os.stat(str(stale)).st_mtime_ns

    # A refused conversion: exits 0, writes nothing.
    monkeypatch.setattr(build_mod, "_run", lambda *a, **k: None)

    with pytest.raises(RuntimeError) as exc:
        build_app(str(app), str(out), self_host=())
    message = str(exc.value)
    assert "did not happen" in message
    assert "earlier build" in message

    # And it really did leave the previous build alone rather than half-writing
    # over it, which is what the message promises.
    assert stale.read_text() == "<html>the previous build</html>"
    assert os.stat(str(stale)).st_mtime_ns == before


# The two tests that used to sit here asserted the old contract -- that a build
# deletes every wheel in the output directory. That contract was the bug: it
# destroyed the wheels of other apps sharing the directory. Replaced by
# test_a_build_keeps_another_apps_wheel and
# test_superseded_version_of_our_own_wheel_is_removed below, which pin down
# both halves of the behaviour that replaced it.


def test_local_wheels_precede_named_requirements(tmp_path, monkeypatch):
    """The model's own wheel must be offered before the names it depends on."""
    app = tmp_path / "a.py"
    app.write_text("DESIGN_WIDTH = 900\n")
    out = tmp_path / "out"
    commands = []

    def fake_run(cmd, cwd=None):
        commands.append(cmd)
        if "wheel" in cmd:
            target = cmd[cmd.index("-w") + 1]
            open(os.path.join(target, "mymodel-0.1-py3-none-any.whl"),
                 "wb").close()
        if "convert" in cmd:
            os.makedirs(out, exist_ok=True)
            (out / "a.html").write_text("")

    monkeypatch.setattr(build_mod, "_run", fake_run)
    build_app(str(app), str(out), packages=[str(tmp_path)],
              requirements=["numpy", "scipy"], self_host=())

    convert = [c for c in commands if "convert" in c][0]
    reqs = convert[convert.index("--requirements") + 1:]
    assert reqs == ["mymodel-0.1-py3-none-any.whl", "numpy", "scipy"]


def test_convert_runs_from_the_output_directory(tmp_path, monkeypatch):
    """Bare wheel filenames only resolve if convert's cwd is outdir."""
    app = tmp_path / "a.py"
    app.write_text("DESIGN_WIDTH = 900\n")
    out = tmp_path / "out"
    seen = {}

    def fake_run(cmd, cwd=None):
        if "convert" in cmd:
            seen["cwd"] = cwd
            os.makedirs(out, exist_ok=True)
            (out / "a.html").write_text("")

    monkeypatch.setattr(build_mod, "_run", fake_run)
    build_app(str(app), str(out), self_host=())
    assert seen["cwd"] == str(out)


# -- shared output directories -------------------------------------------
# Several demos commonly share one output directory so the 35 MB of panel and
# bokeh wheels is paid once rather than per demo. A build must therefore touch
# only its own distributions.

def _fake_build(monkeypatch, out, produces):
    """Stub _run so `pip wheel`/`pip download` write the named wheels."""
    def fake_run(cmd, cwd=None):
        if "wheel" in cmd or "download" in cmd:
            target = cmd[cmd.index("-w") + 1] if "-w" in cmd \
                else cmd[cmd.index("-d") + 1]
            for name in produces.get("wheel" if "wheel" in cmd else "download",
                                     []):
                open(os.path.join(target, name), "wb").close()
        if "convert" in cmd:
            os.makedirs(out, exist_ok=True)
            open(os.path.join(out, "a.html"), "w").close()
    monkeypatch.setattr(build_mod, "_run", fake_run)


def test_a_build_keeps_another_apps_wheel(tmp_path, monkeypatch):
    """The bug this guards: building exercise B deleted exercise A's model
    wheel, so A 404'd in the browser with nothing having failed at build."""
    out = tmp_path / "out"
    out.mkdir()
    neighbour = out / "othermodel-1.0-py3-none-any.whl"
    neighbour.write_bytes(b"")
    app = tmp_path / "a.py"
    app.write_text("DESIGN_WIDTH = 900\n")

    _fake_build(monkeypatch, str(out),
                {"wheel": ["mymodel-0.1-py3-none-any.whl"]})
    build_app(str(app), str(out), packages=[str(tmp_path)], self_host=())

    assert neighbour.exists(), "another app's wheel was deleted"
    assert (out / "mymodel-0.1-py3-none-any.whl").exists()


def test_self_hosted_wheels_do_not_clobber_neighbours(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    neighbour = out / "othermodel-1.0-py3-none-any.whl"
    neighbour.write_bytes(b"")
    app = tmp_path / "a.py"
    app.write_text("DESIGN_WIDTH = 900\n")

    _fake_build(monkeypatch, str(out),
                {"download": ["panel-1.9.4-py3-none-any.whl"]})
    build_app(str(app), str(out), self_host=("panel",))

    assert neighbour.exists()
    assert (out / "panel-1.9.4-py3-none-any.whl").exists()


def test_superseded_version_of_our_own_wheel_is_removed(tmp_path, monkeypatch):
    """Two versions of one distribution in the directory would be ambiguous."""
    out = tmp_path / "out"
    out.mkdir()
    stale = out / "mymodel-0.0.9-py3-none-any.whl"
    stale.write_bytes(b"")
    app = tmp_path / "a.py"
    app.write_text("DESIGN_WIDTH = 900\n")

    _fake_build(monkeypatch, str(out),
                {"wheel": ["mymodel-0.1-py3-none-any.whl"]})
    build_app(str(app), str(out), packages=[str(tmp_path)], self_host=())

    assert not stale.exists(), "stale version of our own distribution kept"
    assert (out / "mymodel-0.1-py3-none-any.whl").exists()


def test_clean_wheels_false_keeps_even_superseded_versions(tmp_path,
                                                          monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    stale = out / "mymodel-0.0.9-py3-none-any.whl"
    stale.write_bytes(b"")
    app = tmp_path / "a.py"
    app.write_text("DESIGN_WIDTH = 900\n")

    _fake_build(monkeypatch, str(out),
                {"wheel": ["mymodel-0.1-py3-none-any.whl"]})
    build_app(str(app), str(out), packages=[str(tmp_path)], self_host=(),
              clean_wheels=False)

    assert stale.exists()


def test_wheel_distribution_normalizes_the_name():
    from artesian.build import wheel_distribution
    # PEP 427 escapes the distribution, so a hyphenated name only ever
    # reaches us underscored -- "scikit-learn-1.0-...whl" cannot occur.
    assert wheel_distribution("scikit_learn-1.0-py3-none-any.whl") \
        == "scikit-learn"
    assert wheel_distribution("/a/b/GRLP-2.1.0-py3-none-any.whl") == "grlp"
    assert wheel_distribution("artesian-0.1.0.dev0-py3-none-any.whl") \
        == "artesian"


# -- warning when a demo will never scale ---------------------------------

def test_warns_when_the_app_declares_no_design_width(tmp_path, monkeypatch):
    """Nothing about the result looks wrong -- it builds, loads and fits its
    frame -- so the only way an author learns is being told."""
    app = tmp_path / "a.py"
    app.write_text("import panel\n")            # no DESIGN_WIDTH
    out = tmp_path / "out"
    _fake_build(monkeypatch, str(out), {})

    with pytest.warns(UserWarning, match="records none"):
        build_app(str(app), str(out), self_host=())


def test_no_warning_when_the_app_declares_one(tmp_path, monkeypatch):
    app = tmp_path / "a.py"
    app.write_text("DESIGN_WIDTH = 900\nimport panel\n")
    out = tmp_path / "out"
    _fake_build(monkeypatch, str(out), {})

    with warnings.catch_warnings():
        warnings.simplefilter("error")           # any warning fails the test
        build_app(str(app), str(out), self_host=())


def test_explicit_design_width_silences_it(tmp_path, monkeypatch):
    app = tmp_path / "a.py"
    app.write_text("import panel\n")
    out = tmp_path / "out"
    _fake_build(monkeypatch, str(out), {})

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        build_app(str(app), str(out), self_host=(), design_width=800)


def test_warns_about_a_stale_neighbour(tmp_path, monkeypatch):
    """Exactly what happened on GeomorphOnline: corestone's demo was built
    after the width started being recorded, GRLP's was not, and the older one
    sat there unscaled with nothing to point it out."""
    out = tmp_path / "out"
    out.mkdir()
    (out / "grlp_panel.html").write_text("<html><head></head></html>")
    app = tmp_path / "a.py"
    app.write_text("DESIGN_WIDTH = 900\nimport panel\n")
    _fake_build(monkeypatch, str(out), {})

    with pytest.warns(UserWarning, match="grlp_panel.html"):
        build_app(str(app), str(out), self_host=())


def test_strip_vendored_refuses_when_the_app_needs_those_bundles(tmp_path,
                                                                 monkeypatch):
    """Better to fail the build than ship a demo whose JavaScript was removed."""
    app = tmp_path / "a.py"
    app.write_text("DESIGN_WIDTH = 900\n")
    out = tmp_path / "out"

    def fake_run(cmd, cwd=None):
        if "convert" in cmd:
            os.makedirs(out, exist_ok=True)
            (out / "a.html").write_text('src="panel/dist/panel.min.js"')
    monkeypatch.setattr(build_mod, "_run", fake_run)

    with pytest.raises(RuntimeError, match="removed JavaScript it needs"):
        build_app(str(app), str(out), self_host=(), strip_vendored=True)


def test_strip_vendored_is_content_when_the_front_end_is_on_a_cdn(tmp_path,
                                                                 monkeypatch):
    app = tmp_path / "a.py"
    app.write_text("DESIGN_WIDTH = 900\n")
    out = tmp_path / "out"

    def fake_run(cmd, cwd=None):
        if "convert" in cmd:
            os.makedirs(out, exist_ok=True)
            (out / "a.html").write_text('src="https://cdn.bokeh.org/x.min.js"')
    monkeypatch.setattr(build_mod, "_run", fake_run)

    build_app(str(app), str(out), self_host=(), strip_vendored=True)
