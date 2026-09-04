"""
What a reader downloads, and making it smaller.

A compiled demo is not a page, it is a Python runtime and a set of wheels, and
on a cold visit that is tens of megabytes. Nobody was surprised by 30 MB of
``panel`` because nothing printed it, which is the first thing fixed here:
:func:`payload` itemises what a build costs, and ``artesian build`` prints it.

The payload divides in two, and the halves want different treatment.

* **Self-hosted.** The wheels beside the app: ``panel``, ``bokeh``, and the
  model's own. Ours to make smaller, and almost all of it is ``panel``.
* **From the Pyodide CDN.** The runtime, the standard library, and any package
  Pyodide bundles (``numpy``, ``scipy``). Shared with every other Pyodide site
  the reader has visited, so it may already be cached; self-hosting it would
  guarantee it is not. Left alone deliberately.

:func:`strip_wheel` attacks the first half. ``panel``'s wheel is 31 % source
maps, TypeScript sources and its own test suite, none of which runs in a
browser. Removing them is measured at 9.4 MB on a 30.3 MB wheel.

A stripped wheel is **not** what ``pip install`` would give you, so this module
refuses to leave that undocumented: every stripped wheel gets a manifest inside
its own ``.dist-info`` saying what was taken out and by what. The failure to
avoid is a file whose name asserts a provenance its contents do not have, which
is exactly how a demo once shipped a dirty working tree under a release
version.

See ``docs/payload.md`` for the measurements this module acts on.
"""

import glob
import os
import re
import shutil
import tempfile
import zipfile

__all__ = ["payload", "format_payload", "strip_wheel", "STRIP_MANIFEST",
           "STRIP_RULES", "VENDORED_RULES", "wheel_internal_references"]

#: Written into a stripped wheel's ``.dist-info``, so the wheel says for itself
#: that it is not the one PyPI published.
STRIP_MANIFEST = "ARTESIAN-STRIPPED.txt"

#: Removed by :func:`strip_wheel`. Source maps exist so a developer can debug
#: minified JavaScript and nothing executes them; ``.ts`` files are the
#: TypeScript the shipped bundles were compiled from; a package's own tests do
#: not run in a reader's browser. ``.d.ts`` is kept: it is a type declaration
#: some tooling reads, it is small, and the saving does not need it.
STRIP_RULES = (
    ("source maps", lambda n: n.endswith(".map")),
    ("TypeScript sources", lambda n: n.endswith(".ts") and not n.endswith(".d.ts")),
    ("test suites", lambda n: "/tests/" in n or n.startswith("tests/")),
)


#: Additionally removes the JavaScript bundles a wheel vendors. This is the
#: large one and the less obvious one, so the reasoning is worth stating.
#:
#: ``panel`` and ``bokeh`` each ship their compiled front end inside the Python
#: wheel, and it dominates: 96 % of ``panel``'s wheel and 78 % of ``bokeh``'s
#: are bundles, against 0.6 and 0.7 MB of Python. But a compiled demo does not
#: load them from there. It loads ``bokeh-*.min.js`` from ``cdn.bokeh.org`` and
#: ``panel.min.js`` from ``cdn.holoviz.org``, and contains no reference to
#: ``panel/dist`` or ``static/js`` at all. The bundles are for serving a page
#: yourself, which is the one thing a compiled demo never does.
#:
#: Measured: 691 files and 11.5 MB off ``panel``, taking a demo's self-hosted
#: payload from 36.85 MB to 15.94 MB.
#:
#: More aggressive than :data:`STRIP_RULES` and separately opt-in, because it
#: rests on that premise about where the front end comes from.
#: :func:`wheel_internal_references` checks the premise against the built app
#: rather than trusting it, and ``build_app`` refuses to finish if it fails.
VENDORED_RULES = STRIP_RULES + (
    ("vendored JS bundles",
     lambda n: (("/dist/" in n or "static/js" in n)
                and n.endswith((".js", ".mjs")))),
)

#: Paths inside a wheel that a compiled app must never reference, if the
#: bundles in that wheel are safe to remove.
_INTERNAL = re.compile(r"(?:panel/dist/|static/js/)[A-Za-z0-9_.\-/]*\.(?:js|mjs)")


def wheel_internal_references(outdir):
    """References from the built app into a wheel's own bundle directories.

    The premise behind :data:`VENDORED_RULES` is that a compiled demo loads its
    front end from a CDN and never out of the wheels beside it. This checks
    that against the generated page and worker instead of assuming it, so the
    strip is refused rather than silently shipping a demo whose JavaScript has
    been taken away.

    Returns a sorted list of the references found; empty means the premise
    holds for this app.
    """
    found = set()
    for pattern in ("*.html", "*.js"):
        for path in glob.glob(os.path.join(outdir, pattern)):
            if os.path.basename(path).startswith("artesian-embed"):
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                found.update(_INTERNAL.findall(fh.read()))
    return sorted(found)


def _wheel_distribution(filename):
    return os.path.basename(filename).split("-")[0]


def strip_wheel(path, rules=STRIP_RULES):
    """Remove non-runtime files from the wheel at ``path``, in place.

    Returns ``(before, after, removed)`` in bytes and file count. A wheel that
    loses nothing is left exactly as it was, rather than rewritten, so a build
    cannot churn a file for no reason.

    The wheel keeps its filename. Renaming it would be more self-evident, but a
    wheel filename is parsed by the installer, and a build tag is not worth the
    risk of an installer in a browser refusing it. Instead the wheel carries
    :data:`STRIP_MANIFEST` inside its own ``.dist-info``, which travels with
    the file and cannot be separated from it.
    """
    before = os.path.getsize(path)
    scratch = tempfile.mkdtemp(prefix="artesian-strip-")
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            drop, kept = [], []
            for name in names:
                label = next((why for why, matches in rules if matches(name)),
                             None)
                (drop if label else kept).append((name, label))
            if not drop:
                return before, before, 0

            counts = {}
            for _, label in drop:
                counts[label] = counts.get(label, 0) + 1

            dist_info = next(
                (n.split("/")[0] for n in names if ".dist-info/" in n), None)
            manifest = _manifest_text(counts, len(drop))

            out = os.path.join(scratch, os.path.basename(path))
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED,
                                 compresslevel=9) as new:
                for name, _ in kept:
                    # A wheel can be stripped again -- conservatively first,
                    # then including the bundles. Carrying the earlier manifest
                    # through would leave two entries of the same name in the
                    # archive, which is legal, ambiguous, and warned about by
                    # the standard library. The one written below describes
                    # everything now missing.
                    if name.endswith("/" + STRIP_MANIFEST):
                        continue
                    new.writestr(zf.getinfo(name), zf.read(name))
                if dist_info:
                    new.writestr("%s/%s" % (dist_info, STRIP_MANIFEST),
                                 manifest)
        shutil.move(out, path)
        return before, os.path.getsize(path), len(drop)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _manifest_text(counts, total):
    lines = [
        "This wheel was modified by artesian and is NOT the file published on",
        "PyPI under this name. Files that no browser executes were removed to",
        "make the download smaller:",
        "",
    ]
    for label in sorted(counts):
        lines.append("  %-22s %d files" % (label, counts[label]))
    lines += [
        "",
        "%d files removed in total. Nothing else was changed: no code was" % total,
        "edited, and no dependency metadata was touched.",
        "",
        "If you need the published wheel, reinstall it from PyPI.",
        "",
    ]
    return "\n".join(lines)


#: Matches the Pyodide runtime the compiled app loads, so the report can name
#: where the rest of the download comes from.
_PYODIDE = re.compile(r"https?://[^\"'\s]*/pyodide/(v[^/]+)/[^\"'\s]*")


def pyodide_source(outdir):
    """``(version, url)`` of the Pyodide runtime the app loads, or ``None``."""
    for js in sorted(glob.glob(os.path.join(outdir, "*.js"))):
        with open(js, encoding="utf-8", errors="replace") as fh:
            found = _PYODIDE.search(fh.read())
        if found:
            return found.group(1), found.group(0)
    return None


def payload(outdir, app=None):
    """What a cold reader downloads from *this* site, itemised, largest first.

    Returns a list of ``(filename, bytes)``. Only the self-hosted half: wheels
    are already DEFLATE-compressed archives, so bytes on disk are bytes on the
    wire, and this is the half that can be made smaller. The Pyodide runtime
    and the packages it bundles are fetched from its CDN and are not counted;
    :func:`pyodide_source` says where from.
    """
    stem = os.path.splitext(os.path.basename(app))[0] if app else None
    items = []
    for path in glob.glob(os.path.join(outdir, "*")):
        name = os.path.basename(path)
        if not os.path.isfile(path):
            continue
        if name.endswith(".whl"):
            items.append((name, os.path.getsize(path)))
        elif stem and name in ("%s.html" % stem, "%s.js" % stem):
            items.append((name, os.path.getsize(path)))
        elif name.startswith("artesian-embed."):
            items.append((name, os.path.getsize(path)))
    return sorted(items, key=lambda item: -item[1])


def format_payload(items, outdir=None):
    """Render :func:`payload` as a table, in decimal MB.

    Decimal, not binary, because that is what a browser's network panel shows
    and the point of printing this is to match what a reader sees.
    """
    if not items:
        return "artesian: nothing to report"
    width = max(len(name) for name, _ in items)
    total = sum(size for _, size in items)
    lines = ["", "  What a cold reader downloads from this site:"]
    for name, size in items:
        share = 100.0 * size / total if total else 0.0
        lines.append("    %-*s  %8.2f MB  %4.1f%%" % (width, name,
                                                      size / 1e6, share))
    lines.append("    %-*s  %8.2f MB" % (width, "total, self-hosted",
                                         total / 1e6))
    if outdir:
        source = pyodide_source(outdir)
        if source:
            lines.append("    plus the Pyodide %s runtime and any package it "
                         "bundles, from its CDN" % source[0])
    lines.append("")
    return "\n".join(lines)
