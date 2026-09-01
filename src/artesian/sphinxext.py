"""
Sphinx extension: build interactive demos as part of the documentation build.

Add to ``conf.py``::

    extensions = ["artesian.sphinxext"]

    artesian_apps = [
        {
            "app": "../interactive_demo/grlp_panel.py",
            "packages": [".."],
            "requirements": ["numpy", "scipy", "networkx"],
            "outdir": "_static/interactive",
        },
    ]

Relative paths are resolved against the Sphinx confdir, so they read the same
way as every other path in ``conf.py``. Each app is compiled at
``builder-inited``, before reading sources, so the output is in place by the
time a page embeds it::

    <iframe src="_static/interactive/grlp_panel.html"
            width="100%" height="760" style="border: none;"></iframe>

Building a WASM app takes tens of seconds and hits PyPI. Set
``artesian_skip_build = True`` (or the environment variable
``ARTESIAN_SKIP_BUILD=1``) to reuse whatever is already in the output
directory – useful for fast local prose edits, and for offline builds.
"""

import os

from sphinx.util import logging

from .build import build_app

logger = logging.getLogger(__name__)

__all__ = ["setup", "build_apps"]

#: Keys accepted in an ``artesian_apps`` entry, mapped to their defaults.
_APP_KEYS = {
    "app": None,               # required
    "outdir": "_static/artesian",
    "packages": (),
    "requirements": (),
    "mode": "pyodide-worker",
    "index": False,
}


def _resolve(confdir, path):
    """Resolve a conf.py-relative path the way Sphinx resolves its own."""
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(confdir, path))


def build_apps(app, config=None):
    """``builder-inited`` handler: compile every configured demo."""
    config = config if config is not None else app.config
    entries = getattr(config, "artesian_apps", None) or []

    skip = (getattr(config, "artesian_skip_build", False)
            or os.environ.get("ARTESIAN_SKIP_BUILD") == "1")
    if skip:
        if entries:
            logger.info("artesian: skipping %d app build(s); reusing "
                        "existing output", len(entries))
        return

    confdir = app.confdir
    for entry in entries:
        unknown = set(entry) - set(_APP_KEYS)
        if unknown:
            raise ValueError(
                "artesian_apps entry has unknown key(s) %s; expected any of %s"
                % (sorted(unknown), sorted(_APP_KEYS)))
        opts = dict(_APP_KEYS)
        opts.update(entry)
        if not opts["app"]:
            raise ValueError("artesian_apps entry is missing required 'app'")

        src = _resolve(confdir, opts["app"])
        outdir = _resolve(confdir, opts["outdir"])
        logger.info("artesian: building %s -> %s", os.path.basename(src),
                    os.path.relpath(outdir, confdir))
        html = build_app(
            src,
            outdir,
            packages=[_resolve(confdir, p) for p in opts["packages"]],
            requirements=opts["requirements"],
            mode=opts["mode"],
            index=opts["index"],
        )
        logger.info("artesian: built %s", os.path.relpath(html, confdir))


def setup(app):
    app.add_config_value("artesian_apps", [], "env")
    app.add_config_value("artesian_skip_build", False, "env")
    app.connect("builder-inited", build_apps)
    from ._version import __version__
    return {"version": __version__,
            "parallel_read_safe": True,
            "parallel_write_safe": True}
