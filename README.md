# artesian

**Compile a Python model into a demo that runs in the reader's browser, with no
server.**

Named for groundwater under enough pressure to reach the surface and flow
without a pump. Your model reaches the reader and runs without a server: it is
compiled to WebAssembly and executes entirely in the browser via
[Pyodide](https://pyodide.org). A demo is then a static file – it costs nothing
to host, it cannot fall over under load, and it keeps working after the grant
ends.

`artesian` was extracted from the machinery behind
[GRLP's interactive demo](https://grlp.readthedocs.io/en/latest/interactive.html)
and [reproduces it exactly](docs/validation.md).

## What it does

Two pieces, usable together or separately.

**A build tool.** Wheels your model straight from its source tree, self-hosts
the `panel` and `bokeh` wheels next to the app, runs `panel convert`, and
rewrites the CDN wheel URLs to the local copies. That last step is not
housekeeping: the holoviz CDN's bokeh wheel currently returns HTTP 403, and
without the rewrite the demo fails to load.

**Thin app helpers.** Only the play/pause timer and reset button that every live
demo rewrites. There is deliberately no model or plotting abstraction – see
[Scope](#scope-what-this-is-not).

## Install

```sh
pip install artesian
```

## First: can your model run in the browser at all?

This is the question to settle before anything else, and it has nothing to do
with `artesian`. Everything your demo imports must be either bundled with
Pyodide or installable from a pure-Python (`py3-none-any`) wheel. A package with
compiled extensions needs a wheel built for Emscripten, and for most scientific
packages none exists.

```sh
artesian check numpy scipy networkx yourmodel
```

```
note  numpy      2.5.2 publishes only platform wheels; bundled by Pyodide
note  scipy      1.18.1 publishes only platform wheels; bundled by Pyodide
ok    networkx   3.6.1 has a pure-Python wheel
FAIL  yourmodel  no such distribution on PyPI

Not installable in the browser: yourmodel
```

Read `note` as "fine if Pyodide bundles it, a blocker otherwise" – that
judgement is left to you rather than guessed at, because Pyodide's bundled set
is version-specific.

The second constraint is speed. A model stepping in milliseconds animates
smoothly at 30 fps; one taking seconds per step wants recompute-on-change
instead of a timer.

## Write the app

A demo is an ordinary [Panel](https://panel.holoviz.org) script ending in
`.servable()`. `artesian.live` supplies the two bits of boilerplate:

```python
import panel as pn
from artesian.live import animator, reset_button

# `sim`, never `state`: panel exports pn.state, and shadowing it fails silently.
sim = {"model": make_model(), "t": 0.}

def step():
    sim["model"].advance(dt)
    source.data = {"x": sim["model"].x, "y": sim["model"].z}

pn.Column(
    pn.Row(animator(step), reset_button(do_reset)),
    slider, fig,
).servable()
```

See [`examples/hillslope.py`](examples/hillslope.py) for a complete one.

### Make the figure fill its container, without changing its shape

A demo gets embedded in containers you do not control – a documentation page, a
course page, a projected slide, a phone – so a figure fixed at some pixel width
is wrong nearly everywhere. `artesian.live.responsive` handles it:

```python
fig = figure(height=380, width=680, ...)   # the proportions you want
responsive(fig)

pn.Column(..., fig, sizing_mode="stretch_width").servable()
```

The trap worth knowing about: the obvious choice, bokeh's `stretch_width`, fills
the width but *pins the height*, so the aspect ratio drifts with the window. A
680×380 plot reads 1.79 as drawn, 2.89 in a 1100 px column, and 4.21 in a
1600 px one. Wherever the meaning lives in a slope – a river's long profile, a
hillslope, a rate through time – that is the same data looking three times
gentler to a reader with a wider monitor.

`responsive()` uses `scale_width` instead, scaling both dimensions so the
exaggeration is identical for everyone, and bounds the result with `max_width`
because preserving the ratio unbounded makes that figure 1342 px tall at
2400 px. Give the enclosing `Column` `sizing_mode="stretch_width"` too, or the
figure has nothing to fill.

## Build it

From the command line:

```sh
artesian build examples/hillslope.py -o _build -p . -r numpy --serve
```

`-p/--package` points at a local source tree to wheel and ship – your model, so
the demo always matches your working tree rather than your last release.
`-r/--requirement` names anything else to resolve in the browser. `--serve`
serves the result, which is how to view it: opening the page over `file://`
trips the browser's cross-origin rules for web workers.

Or from Sphinx, so demos rebuild with the docs. In `conf.py`:

```python
extensions = ["artesian.sphinxext"]

artesian_apps = [
    {
        "app": "../interactive_demo/grlp_panel.py",
        "packages": [".."],
        "requirements": ["numpy", "scipy", "networkx"],
        "outdir": "_static/interactive",
    },
]
```

Make sure `outdir` is somewhere Sphinx actually publishes, or the demo is built
into your source tree and never copied into `_build`:

```python
html_static_path = ["_static"]
```

`artesian` warns if it is not, since the failure is otherwise silent at build
time and a 404 at run time.

Then embed the result in a page:

```html
<iframe src="_static/interactive/grlp_panel.html"
        width="100%" height="760" style="border: none;"></iframe>
```

A build takes tens of seconds and reaches PyPI, so set
`artesian_skip_build = True` (or `ARTESIAN_SKIP_BUILD=1`) to reuse existing
output while editing prose.

### Your model must be importable where the build runs

`panel convert` executes the app in the *building* environment to discover what
it serves, so shipping your model as a wheel for the browser is not enough – it
must also be installed where the build happens. On Read the Docs that means
installing the package in `.readthedocs.yaml`:

```yaml
python:
  install:
    - method: pip
      path: .
    - requirements: docs/requirements.txt
```

If you miss this, `artesian` raises and says so; `panel convert` on its own
fails in a way that is easy to misread.

## Known limitations

- **The Pyodide runtime still comes from a CDN.** The wheels are self-hosted,
  but `pyodide.js` is fetched from `cdn.jsdelivr.net` at load time.
  `panel convert` hardcodes that URL and offers no option to change it, so a
  demo is *not* usable fully offline or behind a firewall blocking jsdelivr.
  Self-hosting it would buy that offline capability and nothing else: the
  reader fetches the same bytes either way, and a docs host is usually slower
  than a CDN.
- **Readers wait 10–30 s on first load** while the browser downloads the Python
  runtime. It is smooth afterwards, and worth saying so on the page. Measured
  for GRLP's demo, that first load is about 63 MB: 11.6 MB of Pyodide core,
  16.6 MB of numpy/scipy/networkx, and 35 MB of self-hosted wheels – of which
  `panel` alone is 28.9 MB, the single largest item and the only real lever on
  load time.
- **Much of the value here is workarounds to current upstream behaviour** – the
  403, the silent `panel convert` failure. That is the argument for a shared
  package (fix once), but it also means this needs to track panel, bokeh, and
  Pyodide releases. It is not fire-and-forget.

## Scope: what this is not

`artesian` does not abstract your model or your plots. A `make_model`/`step`/
`draw` hook contract is easy to write from one model and tends to fit the next
one badly, so it waits for a real second use case to justify it. Build the
figure with bokeh yourself; the library handles getting it into a browser.

## License

GPL-3.0-or-later. Copyright © 2026 Andrew D. Wickert and contributors.
