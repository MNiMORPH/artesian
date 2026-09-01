"""
artesian: compile a Python model into a browser demo that runs with no server.

Named for groundwater under enough pressure to reach the surface and flow
without a pump. The model reaches the reader and runs without a server: it is
compiled to WebAssembly and executes entirely in the browser via Pyodide, so
a demo is a static file, and hosting one costs nothing and keeps running. (The
Pyodide runtime is still fetched from a CDN at load time -- see
:mod:`artesian.build` -- so "no server" means no server of yours, not no
network.)

Two pieces, used together or separately:

- the **build tool** -- :func:`artesian.build_app`, the Sphinx extension
  ``artesian.sphinxext``, and the ``artesian`` command line -- which compiles a
  Panel app plus your model into a self-contained page;
- the **app helpers** in :mod:`artesian.live`, a deliberately thin set covering
  only the play/pause timer and reset button that every live demo rewrites.

Before adapting a model, check that it can run in the browser at all with
:func:`artesian.check_requirements`, or ``artesian check <requirements>``.
"""

from ._version import __version__
from .build import build_app, localize_wheel_urls
from .check import check_requirement, check_requirements, format_report

__all__ = [
    "__version__",
    "build_app",
    "localize_wheel_urls",
    "check_requirement",
    "check_requirements",
    "format_report",
]
