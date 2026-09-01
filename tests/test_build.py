"""build_app() argument handling and its silent-failure guard."""

import os

import pytest

from artesian import build as build_mod
from artesian.build import build_app


def test_rejects_unknown_mode(tmp_path):
    app = tmp_path / "a.py"
    app.write_text("")
    with pytest.raises(ValueError, match="mode must be one of"):
        build_app(str(app), str(tmp_path / "out"), mode="webassembly")


def test_missing_app_is_reported_before_any_work(tmp_path):
    with pytest.raises(FileNotFoundError, match="Panel app not found"):
        build_app(str(tmp_path / "nope.py"), str(tmp_path / "out"))


def test_raises_when_convert_produces_no_page(tmp_path, monkeypatch):
    """`panel convert` can print a failure and still exit 0; a build that
    wrote nothing must not be reported as success."""
    app = tmp_path / "a.py"
    app.write_text("")
    monkeypatch.setattr(build_mod, "_run", lambda *a, **k: None)

    with pytest.raises(RuntimeError) as exc:
        build_app(str(app), str(tmp_path / "out"), self_host=())
    message = str(exc.value)
    assert "did not produce" in message
    assert "importable here" in message      # names the actual cause


def test_stale_wheels_are_cleared_first(tmp_path, monkeypatch):
    """A wheel left by an earlier build must not shadow the fresh one."""
    out = tmp_path / "out"
    out.mkdir()
    stale = out / "grlp-1.0.0-py3-none-any.whl"
    stale.write_bytes(b"")
    app = tmp_path / "a.py"
    app.write_text("")
    monkeypatch.setattr(build_mod, "_run", lambda *a, **k: None)

    with pytest.raises(RuntimeError):          # no page produced; fine
        build_app(str(app), str(out), self_host=())
    assert not stale.exists()


def test_stale_wheels_kept_when_clean_wheels_false(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    stale = out / "grlp-1.0.0-py3-none-any.whl"
    stale.write_bytes(b"")
    app = tmp_path / "a.py"
    app.write_text("")
    monkeypatch.setattr(build_mod, "_run", lambda *a, **k: None)

    with pytest.raises(RuntimeError):
        build_app(str(app), str(out), self_host=(), clean_wheels=False)
    assert stale.exists()


def test_local_wheels_precede_named_requirements(tmp_path, monkeypatch):
    """The model's own wheel must be offered before the names it depends on."""
    app = tmp_path / "a.py"
    app.write_text("")
    out = tmp_path / "out"
    commands = []

    def fake_run(cmd, cwd=None):
        commands.append(cmd)
        if "wheel" in cmd:
            os.makedirs(out, exist_ok=True)
            (out / "mymodel-0.1-py3-none-any.whl").write_bytes(b"")
        if "convert" in cmd:
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
    app.write_text("")
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
