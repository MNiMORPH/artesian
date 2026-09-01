"""
Will this model run in the browser at all?

That is the first question to settle for any candidate model, and it is cheap
to get wrong expensively: the build succeeds, the page loads, and Pyodide only
then fails to find a wheel it can install. Everything the demo imports has to
be either bundled with Pyodide or installable from a pure-Python
(``py3-none-any``) wheel. A package with compiled extensions needs a wheel
built for Emscripten, and for most scientific packages none exists.

:func:`check_requirements` asks PyPI which wheels a distribution publishes and
reports each one as pure-Python, platform-specific, or absent. It deliberately
does *not* consult a Pyodide lockfile: that is version-specific, and a package
Pyodide bundles (numpy, scipy) will be reported here as platform-specific,
which is correct about PyPI and says nothing about Pyodide. So read a
``platform-specific`` verdict as "fine if Pyodide bundles it, otherwise a
blocker" -- which is exactly the judgement a person needs to make.
"""

import json
import urllib.error
import urllib.request

__all__ = ["PURE", "PLATFORM", "MISSING", "check_requirement",
           "check_requirements", "format_report"]

PURE = "pure-python"
PLATFORM = "platform-specific"
MISSING = "not-on-pypi"

#: Bundled with Pyodide itself, so a PLATFORM verdict on these is harmless.
#: Indicative, not exhaustive -- Pyodide's set grows and is version-dependent.
PYODIDE_BUNDLED = frozenset({
    "numpy", "scipy", "pandas", "matplotlib", "networkx", "sympy",
    "scikit-learn", "statsmodels", "pillow", "pyyaml", "regex", "sqlalchemy",
    "xarray", "astropy", "shapely", "bokeh", "panel", "param", "pyparsing",
})


def _pypi_json(name, timeout):
    url = "https://pypi.org/pypi/%s/json" % name
    with urllib.request.urlopen(url, timeout=timeout) as fh:
        return json.load(fh)


def check_requirement(name, timeout=10):
    """Classify one requirement. Returns ``(name, verdict, detail)``."""
    base = name.split("[")[0].split("==")[0].split(">")[0].split("<")[0].strip()
    try:
        data = _pypi_json(base, timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return (base, MISSING, "no such distribution on PyPI")
        return (base, MISSING, "PyPI returned HTTP %d" % exc.code)
    except Exception as exc:
        return (base, MISSING, "could not reach PyPI: %s" % exc)

    version = data["info"]["version"]
    files = data["releases"].get(version, [])
    wheels = [f["filename"] for f in files if f["filename"].endswith(".whl")]
    if any(w.endswith("-py3-none-any.whl") or w.endswith("-py2.py3-none-any.whl")
           for w in wheels):
        return (base, PURE, "%s has a pure-Python wheel" % version)
    if wheels:
        return (base, PLATFORM, "%s publishes only platform wheels%s"
                % (version,
                   "; bundled by Pyodide" if base.lower() in PYODIDE_BUNDLED
                   else ""))
    return (base, PLATFORM, "%s publishes no wheel (sdist only)" % version)


def check_requirements(names, timeout=10):
    """Classify each of ``names``. Returns a list of ``(name, verdict, detail)``."""
    return [check_requirement(n, timeout) for n in names]


def format_report(results):
    """Render :func:`check_requirements` output as aligned lines."""
    marks = {PURE: "ok  ", PLATFORM: "note", MISSING: "FAIL"}
    width = max([len(r[0]) for r in results] + [1])
    lines = ["%s  %-*s  %s" % (marks.get(v, "?   "), width, n, d)
             for n, v, d in results]
    blockers = [n for n, v, _ in results if v == MISSING]
    if blockers:
        lines.append("")
        lines.append("Not installable in the browser: %s" % ", ".join(blockers))
    return "\n".join(lines)
