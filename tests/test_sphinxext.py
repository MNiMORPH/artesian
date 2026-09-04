"""Sphinx wiring: config validation, path resolution, and the skip switch."""

import os

import pytest

from artesian import sphinxext


class FakeApp:
    """Just enough Sphinx application for build_apps()."""

    def __init__(self, confdir):
        self.confdir = str(confdir)


class FakeConfig:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_unknown_key_is_rejected_by_name(tmp_path):
    """A typo in conf.py must not silently yield a missing demo."""
    cfg = FakeConfig(artesian_apps=[{"app": "a.py", "reqirements": []}])
    with pytest.raises(ValueError) as exc:
        sphinxext.build_apps(FakeApp(tmp_path), cfg)
    assert "reqirements" in str(exc.value)
    assert "requirements" in str(exc.value)     # names the valid spelling


def test_missing_app_key_is_rejected(tmp_path):
    cfg = FakeConfig(artesian_apps=[{"outdir": "_static/demo"}])
    with pytest.raises(ValueError, match="missing required 'app'"):
        sphinxext.build_apps(FakeApp(tmp_path), cfg)


def test_skip_flag_builds_nothing(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(sphinxext, "build_app",
                        lambda *a, **k: called.append(a))
    cfg = FakeConfig(artesian_apps=[{"app": "a.py"}], artesian_skip_build=True)
    sphinxext.build_apps(FakeApp(tmp_path), cfg)
    assert called == []


def test_skip_via_environment_variable(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(sphinxext, "build_app",
                        lambda *a, **k: called.append(a))
    monkeypatch.setenv("ARTESIAN_SKIP_BUILD", "1")
    cfg = FakeConfig(artesian_apps=[{"app": "a.py"}])
    sphinxext.build_apps(FakeApp(tmp_path), cfg)
    assert called == []


def test_paths_resolve_against_confdir(tmp_path, monkeypatch):
    """conf.py-relative paths must behave like every other Sphinx path."""
    seen = {}

    def fake_build(app, outdir, **kw):
        seen.update(app=app, outdir=outdir, **kw)
        return os.path.join(outdir, "x.html")

    monkeypatch.setattr(sphinxext, "build_app", fake_build)
    confdir = tmp_path / "docs"
    confdir.mkdir()
    cfg = FakeConfig(artesian_apps=[{
        "app": "../demo/app.py",
        "outdir": "_static/demo",
        "packages": [".."],
        "requirements": ["numpy"],
    }])
    sphinxext.build_apps(FakeApp(confdir), cfg)

    assert seen["app"] == str(tmp_path / "demo" / "app.py")
    assert seen["outdir"] == str(confdir / "_static" / "demo")
    assert seen["packages"] == [str(tmp_path)]
    assert seen["requirements"] == ["numpy"]     # passed through untouched


def test_absolute_paths_are_left_absolute(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(sphinxext, "build_app",
                        lambda app, outdir, **kw: seen.update(
                            app=app, outdir=outdir) or "x")
    absolute = str(tmp_path / "elsewhere" / "app.py")
    cfg = FakeConfig(artesian_apps=[{"app": absolute, "outdir": "/tmp/out"}])
    sphinxext.build_apps(FakeApp(tmp_path), cfg)
    assert seen["app"] == absolute
    assert seen["outdir"] == "/tmp/out"


def test_no_apps_configured_is_a_noop(tmp_path):
    sphinxext.build_apps(FakeApp(tmp_path), FakeConfig())


def test_setup_registers_config_values_and_hook():
    registered, connected = {}, []
    class App:
        def add_config_value(self, name, default, rebuild):
            registered[name] = default
        def connect(self, event, handler):
            connected.append(event)
    meta = sphinxext.setup(App())
    assert registered == {"artesian_apps": [], "artesian_skip_build": False}
    assert connected == ["builder-inited"]
    assert meta["parallel_read_safe"]


def _capture_warnings(monkeypatch):
    warnings = []
    monkeypatch.setattr(sphinxext.logger, "warning",
                        lambda msg, *a: warnings.append(msg % a))
    monkeypatch.setattr(sphinxext, "build_app",
                        lambda app, outdir, **kw: os.path.join(outdir, "x.html"))
    return warnings


def test_warns_when_outdir_is_not_in_html_static_path(tmp_path, monkeypatch):
    """Output outside html_static_path never reaches _build; the page 404s at
    run time with nothing having failed at build time."""
    warnings = _capture_warnings(monkeypatch)
    (tmp_path / "_static" / "demo").mkdir(parents=True)
    cfg = FakeConfig(artesian_apps=[{"app": "a.py", "outdir": "_static/demo"}],
                     html_static_path=[])
    sphinxext.build_apps(FakeApp(tmp_path), cfg)
    assert len(warnings) == 1
    assert "404" in warnings[0]
    assert "'_static'" in warnings[0]        # names the entry to add


def test_no_warning_when_covered_by_html_static_path(tmp_path, monkeypatch):
    warnings = _capture_warnings(monkeypatch)
    cfg = FakeConfig(artesian_apps=[{"app": "a.py", "outdir": "_static/demo"}],
                     html_static_path=["_static"])
    sphinxext.build_apps(FakeApp(tmp_path), cfg)
    assert warnings == []


def test_no_warning_when_outdir_is_exactly_a_static_path(tmp_path, monkeypatch):
    warnings = _capture_warnings(monkeypatch)
    cfg = FakeConfig(artesian_apps=[{"app": "a.py", "outdir": "_static"}],
                     html_static_path=["_static"])
    sphinxext.build_apps(FakeApp(tmp_path), cfg)
    assert warnings == []


def test_similarly_named_static_dir_does_not_count_as_covering(tmp_path,
                                                              monkeypatch):
    """'_static_extra/demo' must not be considered covered by '_static'."""
    warnings = _capture_warnings(monkeypatch)
    (tmp_path / "_static_extra" / "demo").mkdir(parents=True)
    cfg = FakeConfig(
        artesian_apps=[{"app": "a.py", "outdir": "_static_extra/demo"}],
        html_static_path=["_static"])
    sphinxext.build_apps(FakeApp(tmp_path), cfg)
    assert len(warnings) == 1


def test_no_warning_for_outdir_outside_the_docs_tree(tmp_path, monkeypatch):
    """Somewhere else entirely is the user's business, not ours to police."""
    warnings = _capture_warnings(monkeypatch)
    cfg = FakeConfig(artesian_apps=[{"app": "a.py", "outdir": "../elsewhere"}],
                     html_static_path=["_static"])
    sphinxext.build_apps(FakeApp(tmp_path), cfg)
    assert warnings == []


def test_strip_wheels_is_passed_through_and_defaults_off(tmp_path,
                                                         monkeypatch):
    """Off unless asked for: a stripped wheel is not what PyPI published."""
    seen = {}
    monkeypatch.setattr(sphinxext, "build_app",
                        lambda app, outdir, **kw: seen.update(kw)
                        or os.path.join(outdir, "x.html"))
    monkeypatch.setattr(sphinxext, "payload", lambda *a, **k: [])
    monkeypatch.setattr(sphinxext, "format_payload", lambda *a, **k: "")

    cfg = FakeConfig(artesian_apps=[{"app": "a.py"}], html_static_path=[])
    sphinxext.build_apps(FakeApp(tmp_path), cfg)
    assert seen["strip_wheels"] is False

    seen.clear()
    cfg = FakeConfig(artesian_apps=[{"app": "a.py", "strip_wheels": True}],
                     html_static_path=[])
    sphinxext.build_apps(FakeApp(tmp_path), cfg)
    assert seen["strip_wheels"] is True


def test_no_warning_on_a_first_build(tmp_path, monkeypatch):
    """Sphinx drops html_static_path entries that do not exist when it reads
    the configuration, and artesian creates the directory afterwards. So on a
    first build a correctly configured project looks misconfigured, and the
    warning would tell someone to add an entry they already added."""
    warnings = _capture_warnings(monkeypatch)
    cfg = FakeConfig(artesian_apps=[{"app": "a.py", "outdir": "_static/demo"}],
                     html_static_path=[])          # pruned by Sphinx
    sphinxext.build_apps(FakeApp(tmp_path), cfg)   # _static/demo absent
    assert warnings == []
