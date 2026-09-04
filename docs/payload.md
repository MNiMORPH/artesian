# What a reader actually downloads, and what to do about it

Written 2026-09-04 after Andy looked at a demo's network panel and was
surprised. Everything below is measured, on this machine, at
`artesian` `5a7c1ed`, `panel` 1.9.4, `bokeh` 3.9.2, Pyodide 0.29.3.

## The number

**About 52 MB for one demo, on a cold visit.** Itemised:

| | MB | from | notes |
|---|---|---|---|
| `panel` wheel | **30.33** | this site | **58% of the whole payload** |
| Pyodide `.asm.wasm` | 8.65 | jsdelivr CDN | |
| `bokeh` wheel | **6.41** | this site | |
| `numpy` wheel | 3.10 | jsdelivr CDN | |
| Python stdlib zip | 2.42 | jsdelivr CDN | |
| Pyodide `.asm.js` | 1.07 | jsdelivr CDN | |
| `pyodide-lock.json` | 0.12 | jsdelivr CDN | |
| `packaging`, `micropip` | 0.07 | jsdelivr CDN | |
| the app itself | 0.05 | this site | `.html` + `.js` |
| the model's own wheel | 0.03 | this site | `hillcreep`, for scale |
| `artesian` wheel | 0.04 | this site | |

Two things worth separating, because they are easy to conflate:

- **12.3 MB is the Pyodide runtime from jsdelivr**, and it is shared with
  *every other Pyodide site the reader has visited*. Leave it alone. It is also
  the one part that a browser is most likely to already have.
- **36.8 MB is self-hosted by us**, and it is almost entirely `panel` and
  `bokeh`. This is the part worth attacking.

Note that a browser's network panel may report a larger figure than 52 MB: it
counts decompressed sizes for text resources and includes traffic the worker
issues. The table above is transfer bytes.

## Where `panel`'s 30 MB goes

Uncompressed, the wheel is dominated by one directory:

```
panel/dist   107 MB      compiled JS bundles, source maps, TypeScript sources
panel/tests    2 MB
everything else ~ 5 MB
```

By file type: 697 `.js`, 363 `.py`, **241 `.ts`**, **217 `.map`**, 195 `.css`.

The `.map` files are source maps: they exist so a developer can debug minified
JavaScript in devtools, and nothing executes them. The `.ts` files are the
TypeScript the bundles were compiled *from*. Neither is needed to run.

## Tested: stripping non-runtime files from `panel` saves 9.4 MB

Removing `*.map`, `*.ts` (keeping `*.d.ts`) and `panel/tests`:

```
panel wheel   30.33 MB  ->  20.97 MB      saving 9.36 MB, 31% of the wheel
one demo      52.3 MB   ->  42.9 MB       saving 18% of the whole payload
```

476 files removed. **Verified to still work**: the hillslope demo was rebuilt
against the stripped wheel, booted under Pyodide in a real browser, ran, and
reported the correct diffusivity, with zero console errors.

`bokeh` has no comparable win. It ships no source maps, and stripping the same
categories changed its wheel by under 1% — re-zipping alone accounts for that.
Its 6.4 MB looks close to irreducible.

## What I would suggest artesian do

Roughly in order of payoff per unit of risk.

**1. `--strip-wheels`, off by default.** Post-process the self-hosted wheels to
drop source maps, TypeScript sources and test suites, then rewrite the wheel.
Measured 9.4 MB. The reason to default it *off* is provenance: a stripped
`panel-1.9.4-py3-none-any.whl` is no longer what `pip install panel==1.9.4`
gives, while carrying a filename that says it is. If artesian does this it
should say so where a reader can find it, and the exercise-provenance table
should record that the wheel was stripped.

Untested, and worth checking before shipping: whether any panel feature these
demos do not use needs those files. Source maps are certainly safe. The `.ts`
sources are very probably safe. `panel/tests` is safe.

**2. Ask whether the demo needs `panel` at all.** This is the big one and the
most work. `panel` is 58% of the payload, and a demo like the ones built so far
uses a vanishing fraction of it: a few sliders, a toggle, a button, a Markdown
pane and a Column. Everything that *draws* is bokeh, which the app already
imports directly. A thin bokeh-only path — widgets and layout built from
`bokeh.models` and served through `bokeh`'s own standalone embedding — would
cut the payload roughly in half again, to about 22 MB.

That is a second front end for artesian to maintain, not a flag, so it should
not be attempted on a hunch. But it is where the remaining bulk is, and
`artesian.live` is already the whole of what these demos use panel *for*.

**3. Say what it costs, in the tool.** `artesian build` finishes by printing
where it wrote the page. It could also print the payload a cold reader will
download, itemised as above. Nobody was surprised by 30 MB of panel because it
is hidden; it is hidden because nothing prints it.

## The other axis: memory, which is not the same problem

Transfer is paid once and cached. **Memory is paid every time, per runtime.**

Measured, as resident memory of the whole browser process tree, before and
after the demos boot:

```
one demo       + 674 MB
two demos      +1107 MB      (the second costs 433 MB, not another 674)
```

The second demo costs less than the first because compiled WASM and shared
library pages are reused. What is not reused is the Python heap.

**Two demos in two iframes on one page cannot share a runtime.** They are
separate browsing contexts with separate WASM instances, and sharing memory
across them needs `SharedArrayBuffer`, which needs COOP/COEP response headers,
which GitHub Pages gives no way to set. The only way to have one runtime is one
document: a single app containing both models, e.g. behind a tab strip.

This matters for pages that embed more than one demo. `loading="lazy"` on the
frames defers the second until the reader scrolls to it, which helps the reader
who never gets that far and not at all the reader who does.

## What not to do

- **Do not gzip the wheels.** They are already DEFLATE-compressed zips; a
  second pass gains nothing and GitHub Pages will not serve a `.gz` as a wheel.
- **Do not self-host the Pyodide runtime** to "save a request". It is 12.3 MB
  that jsdelivr is already serving to every Pyodide site, so a reader may
  well have it cached; self-hosting guarantees they do not.
- **Do not change a wheel's contents while keeping its filename**, unless the
  provenance record says so. See `exercises/apps/README.md` in
  GeomorphOnline.github.io for the related trap: because a model wheel's
  filename never changes between builds, browsers reinstall the previous one.
  A silently stripped `panel` wheel would be the same failure with a
  third-party package.

## Reproducing these numbers

- Self-hosted sizes: `ls -l` on the build output. Wheels are already
  compressed, so bytes on disk are bytes on the wire.
- CDN sizes: `curl -sIL https://cdn.jsdelivr.net/pyodide/v0.29.3/full/<file>`
  and read `content-length`.
- Memory: total RSS of the browser process tree, sampled before navigation and
  after the app's Run button appears with the `pn-loading` class gone.
- The strip test: unzip the wheel, `find -name '*.map' -delete`,
  `find -name '*.ts' -not -name '*.d.ts' -delete`, `rm -rf panel/tests`,
  re-zip, drop it into a built app directory in place of the original, and
  drive the page in a browser.

Do not trust CDP `Network.*` events for the total: in `pyodide-worker` mode the
wheels are fetched by a Web Worker, whose requests do not appear in the page's
session. That undercount is what made this look like 2 MB on the first attempt.
