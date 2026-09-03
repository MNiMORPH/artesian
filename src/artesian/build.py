"""
Compile a Panel app into a self-contained WebAssembly page.

The output directory holds the generated HTML/JS, a freshly built wheel of your
model, and self-hosted copies of the ``panel``/``bokeh`` wheels, all referenced
by *relative* URLs. The page therefore works wherever it is served, without
depending on a wheel CDN staying up or serving a 200.

One external dependency remains and is worth stating plainly: the Pyodide
runtime itself is still fetched from ``cdn.jsdelivr.net`` at load time.
``panel convert`` hardcodes that URL and offers no option to change it, so a
demo built this way is *not* usable fully offline or behind a firewall that
blocks jsdelivr. artesian does not self-host it today.

Self-hosting would buy only that offline capability, not a smaller download:
the reader fetches the same bytes either way, and from a docs host rather
than a CDN they may well arrive slower. The cost is smaller than it sounds --
Pyodide fetches packages on demand rather than shipping its whole
distribution, so the core runtime is about 11.6 MB (measured against
v0.29.3: pyodide.js, pyodide.asm.js, pyodide.asm.wasm, python_stdlib.zip)
plus each package used. For scale, the panel wheel self-hosted here is
28.9 MB on its own, and is the single largest item a reader downloads.

The one non-obvious step is :func:`localize_wheel_urls`. ``panel convert`` emits
absolute ``https://cdn.holoviz.org/...`` URLs for the panel and bokeh wheels;
the CDN's bokeh wheel currently returns HTTP 403, which breaks the app at load
time. Rewriting those URLs to the co-located copies fixes it and removes the
CDN from the run-time path.
"""

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import warnings

from .embed import (declared_design_width, inject_design_width,
                    unscaled_pages, write_embed_script)

__all__ = ["build_app", "localize_wheel_urls"]

#: ``panel convert`` targets we accept. ``pyodide-worker`` runs the model on a
#: web worker, so a slow time step cannot freeze the page; ``pyodide`` runs it
#: on the main thread. Prefer the worker unless something needs the DOM.
MODES = ("pyodide-worker", "pyodide")

#: Packages whose wheels are downloaded and served alongside the app rather
#: than pulled from a CDN at run time.
DEFAULT_SELF_HOST = ("panel", "bokeh")


def _run(cmd, cwd=None):
    """Run a subprocess, raising with its output attached if it fails."""
    subprocess.run(cmd, cwd=cwd, check=True)


def wheel_distribution(filename):
    """The PEP 503-normalized distribution name from a wheel filename.

    A wheel is ``{distribution}-{version}-...-.whl`` and a distribution name
    cannot itself contain a hyphen, so everything before the first one is the
    name. Normalizing lets ``scikit_learn-...`` and ``scikit-learn`` compare
    equal, which is how they are the same package.
    """
    base = os.path.basename(filename).split("-")[0]
    return re.sub(r"[-_.]+", "-", base).lower()


def _prune_superseded(outdir, keep):
    """Drop wheels of the same distribution as ``keep`` but a different file.

    Removes a stale *version* of what we just wrote, and nothing else -- other
    apps sharing this directory keep their own wheels.
    """
    target = wheel_distribution(keep)
    for old in glob.glob(os.path.join(outdir, "*.whl")):
        if os.path.basename(old) != keep and wheel_distribution(old) == target:
            os.remove(old)


def _installed_version(package):
    """Version of ``package`` in the *building* environment, or None."""
    try:
        from importlib.metadata import version
        return version(package)
    except Exception:
        return None


def build_app(app, outdir, packages=(), requirements=(), mode="pyodide-worker",
              self_host=DEFAULT_SELF_HOST, index=False, clean_wheels=True,
              design_width=None):
    """Compile ``app`` into a standalone WebAssembly page in ``outdir``.

    Parameters
    ----------
    app : path
        The Panel application source (a ``.py`` file ending in ``.servable()``).
    outdir : path
        Directory to write the compiled app and its wheels into. Created if
        needed. For a Sphinx project this is typically ``_static/<something>``.
    packages : sequence of path, optional
        Local source trees to build wheels from and ship with the app – your
        model. Each is passed to ``pip wheel --no-deps``, so the wheel always
        matches the working tree rather than the last PyPI release.
    requirements : sequence of str, optional
        Additional requirements resolved in the browser: either names Pyodide
        bundles (``numpy``, ``scipy``) or anything with a pure-Python wheel on
        PyPI. Use :func:`artesian.check.check_requirements` when unsure.
    mode : {'pyodide-worker', 'pyodide'}, optional
        ``panel convert`` target. See :data:`MODES`.
    self_host : sequence of str, optional
        Packages to download from PyPI and serve next to the app instead of
        from a CDN. Versions are matched to the building environment so the
        compiled app and its runtime agree.
    index : bool, optional
        Also emit ``index.html`` (``panel convert --index``) when several apps
        share ``outdir``.
    clean_wheels : bool, optional
        Remove *superseded versions of this build's own distributions* from
        ``outdir``, so a stale wheel cannot shadow the fresh one. Wheels
        belonging to other apps sharing the directory are never touched: that
        sharing is what keeps a multi-demo site to one 35 MB copy of panel and
        bokeh instead of one per demo.
    design_width : int, optional
        The width the app is laid out for, in CSS pixels. Recorded in the
        compiled page so the embedding script scales the demo above that width
        instead of stretching it. Defaults to a module-level ``DESIGN_WIDTH``
        in the app if it declares one, which is the way to keep the number in
        one place -- see :func:`artesian.embed.declared_design_width`. Without
        either, the demo is fitted to the page but never scaled.

    Returns
    -------
    str
        Path to the generated HTML page, ready to embed in an ``<iframe>``.
    """
    if mode not in MODES:
        raise ValueError("mode must be one of %r, got %r" % (MODES, mode))
    app = os.path.abspath(app)
    if not os.path.exists(app):
        raise FileNotFoundError("Panel app not found: %s" % app)
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)

    # Build each local package's wheel in a scratch directory and move it in,
    # rather than building into outdir and diffing the listing. Several apps
    # commonly share one output directory (a course site, a docs site with
    # more than one demo) so that the 35 MB of panel and bokeh wheels is paid
    # once; this way a build only ever touches its own distributions and
    # leaves its neighbours' wheels alone. --no-deps keeps each wheel to the
    # package itself: its dependencies are declared through `requirements`,
    # because in the browser they come from Pyodide, not from pip.
    local_wheels = []
    for pkg in packages:
        scratch = tempfile.mkdtemp(prefix="artesian-wheel-")
        try:
            _run([sys.executable, "-m", "pip", "wheel", os.path.abspath(pkg),
                  "--no-deps", "-w", scratch])
            built = sorted(glob.glob(os.path.join(scratch, "*.whl")))
            if not built:
                raise RuntimeError("pip wheel produced no wheel for %s" % pkg)
            for src in built:
                name = os.path.basename(src)
                if clean_wheels:
                    _prune_superseded(outdir, name)
                shutil.move(src, os.path.join(outdir, name))
                local_wheels.append(name)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    # Self-host the runtime wheels at the versions this environment has, so the
    # page never depends on a CDN being up (or on it serving a 200).
    for name in self_host:
        pinned = _installed_version(name)
        spec = "%s==%s" % (name, pinned) if pinned else name
        scratch = tempfile.mkdtemp(prefix="artesian-host-")
        try:
            _run([sys.executable, "-m", "pip", "download", spec, "--no-deps",
                  "-d", scratch])
            for src in sorted(glob.glob(os.path.join(scratch, "*.whl"))):
                basename = os.path.basename(src)
                if clean_wheels:
                    _prune_superseded(outdir, basename)
                dest = os.path.join(outdir, basename)
                if os.path.exists(dest):
                    os.remove(dest)
                shutil.move(src, dest)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    # `panel convert` resolves bare wheel filenames relative to its working
    # directory, so run it from outdir and pass the wheels by basename.
    cmd = [sys.executable, "-m", "panel", "convert", app,
           "--to", mode, "--out", outdir]
    if index:
        cmd.append("--index")
    reqs = list(local_wheels) + list(requirements)
    if reqs:
        cmd += ["--requirements"] + reqs
    _run(cmd, cwd=outdir)

    # `panel convert` reports some failures on stdout and still exits 0, so a
    # zero return code is not evidence that anything was written. Check for the
    # page itself.
    stem = os.path.splitext(os.path.basename(app))[0]
    page = os.path.join(outdir, "%s.html" % stem)
    if not os.path.exists(page):
        raise RuntimeError(
            "panel convert did not produce %s.\n"
            "It runs your app in *this* environment to discover what it "
            "serves, so every module the app imports -- including your model "
            "-- must be importable here, not merely shipped as a wheel for "
            "the browser. Install the model into the building environment "
            "(e.g. `pip install -e %s`) and rebuild.\n"
            "Check the panel convert output above for the failing import."
            % (page, packages[0] if packages else "."))

    localize_wheel_urls(outdir, ("%s.js" % stem, "%s.html" % stem))

    # The page-side half of the demo: how the embedding page sizes and scales
    # the frame. Emitted rather than left to each page to copy, because it
    # carries fixes no one would rediscover -- see artesian/embed.py.
    write_embed_script(outdir)
    width = design_width if design_width is not None \
        else declared_design_width(app)
    if width:
        inject_design_width(page, width)
    else:
        # Worth saying out loud, because nothing about the result looks wrong.
        # The demo builds, loads, and fits its frame; it simply never scales,
        # so its text and controls keep their size while the plot grows and on
        # a wide screen they end up small beside it.
        warnings.warn(
            "%s declares no DESIGN_WIDTH and none was given, so this demo will "
            "be fitted to the page but never scaled: its text and controls "
            "keep their size while the plot grows. Add `DESIGN_WIDTH = <px>` "
            "at module level in the app, or pass design_width=."
            % os.path.basename(app), stacklevel=2)

    # Demos share an output directory, so one built before artesian recorded
    # the width -- or never rebuilt since -- sits there silently unscaled
    # beside newer ones. Only rebuilding it fixes that, and nothing else will
    # ever point it out.
    stale = unscaled_pages(outdir, exclude=[page])
    if stale:
        warnings.warn(
            "%s in %s record no design width, so they are fitted but never "
            "scaled. They predate this being recorded, or have not been "
            "rebuilt since. Rebuild each one to bring it in line."
            % (", ".join(stale), outdir), stacklevel=2)
    return page


def localize_wheel_urls(outdir, filenames=None):
    """Point absolute wheel URLs at the co-located copies in ``outdir``.

    ``panel convert`` writes CDN URLs for the panel and bokeh wheels. Any URL
    whose final path segment matches a ``.whl`` sitting in ``outdir`` is
    rewritten to that bare filename, which the browser then resolves relative
    to the page. Wheels we did not download are left alone.

    Returns the list of files actually modified.
    """
    wheels = [os.path.basename(w)
              for w in glob.glob(os.path.join(outdir, "*.whl"))]
    if not wheels:
        return []
    if filenames is None:
        filenames = [os.path.basename(f)
                     for f in glob.glob(os.path.join(outdir, "*.js"))
                     + glob.glob(os.path.join(outdir, "*.html"))]

    # Two independent guards against rewriting `.../extra-panel-1.9.3.whl` as
    # `panel-1.9.3.whl` when both wheels are present: the `/` before the name
    # anchors the match to a whole path segment, and longest-first ordering
    # gives the longer filename its chance before the shorter one. Either alone
    # suffices; removing both corrupts the URL (tests/test_localize.py).
    patterns = [
        (re.compile(r"https?://[^\"'\s]*?/" + re.escape(w)), w)
        for w in sorted(wheels, key=len, reverse=True)
    ]

    changed = []
    for name in filenames:
        path = os.path.join(outdir, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            text = original = fh.read()
        for pattern, wheel in patterns:
            text = pattern.sub(wheel, text)
        if text != original:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            changed.append(name)
    return changed
