# Changelog

All notable changes to this project are documented here, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `artesian.embed`: every build now writes an `artesian-embed.css` and an
  `artesian-embed.js` beside the compiled app, shared by every demo in that
  directory. A page embeds a demo with a stylesheet link, an
  `<iframe data-artesian>` and a script tag, and inherits later fixes instead
  of carrying a copy of the sizing logic. The stylesheet is separate because
  it has to apply before any script can run: the script cannot size a frame
  whose document has not loaded, and a demo pulling tens of megabytes of
  Pyodide leaves that window open for many seconds.
- `build_app(design_width=...)` and `--design-width`. The width an app is laid
  out for is read from a module-level `DESIGN_WIDTH` in the app itself and
  recorded in the compiled page. The embedding page should also carry it as
  `data-design-width` on the frame, and that takes precedence: the compiled
  page cannot be read while the embedding page lays itself out, since an
  iframe starts on a blank document and on WebKit that is what a page script
  sees.

### Fixed

- Demos ran off the side of the page on an iPad. Every browser there is WebKit
  underneath, and WebKit sizes an iframe to its content rather than honouring
  `width: 100%`; against an app in `stretch_width` that is a loop with no fixed
  point. The emitted script uses `width: 1px` with `min-width: 100%`, which
  WebKit honours. No desktop engine shows the problem, so it reached two live
  exercises first.

- `build_app()`: wheel a local model, self-host the panel/bokeh wheels, run
  `panel convert`, and localize the wheel URLs, in one call.
- `artesian.sphinxext`: a Sphinx extension driven by an `artesian_apps` list,
  so demos rebuild with the documentation. `artesian_skip_build` (or
  `ARTESIAN_SKIP_BUILD=1`) reuses existing output.
- `artesian` command line: `build` (with `--serve`) and `check`.
- `check_requirements()`: report whether each requirement can install in the
  browser, before a build is attempted.
- `artesian.live`: `animator()`, `reset_button()` and `responsive()` – the
  Panel boilerplate every live demo rewrites. `responsive()` makes a figure
  fill its container while holding its aspect ratio, so the vertical
  exaggeration a reader sees does not depend on their window width.
- `examples/hillslope.py`: a complete demo of a model unrelated to the one
  artesian was extracted from.
- A warning when the output directory is not covered by `html_static_path`,
  which would otherwise build successfully and 404 at run time.

- `build_app` warns when a demo will never scale: when the app declares no
  `DESIGN_WIDTH`, and when another compiled page in the same output directory
  records none. Such a page still builds, loads and fits its frame, so nothing
  reveals it otherwise.
- `artesian.embed.page_design_width` and `artesian.embed.unscaled_pages` expose
  that check.

- `artesian.payload`: `payload()` and `format_payload()` itemise what a cold
  reader downloads, printed after every build and logged in a Sphinx build.
- `--strip-wheels` / `strip_wheels=`: remove source maps, TypeScript sources
  and test suites from the self-hosted wheels, measured at 9.4 MB off `panel`.
  Off by default; each stripped wheel records the change in its own
  `.dist-info`.

### Notes

- Extracted from the build hook in [GRLP](https://github.com/MNiMORPH/GRLP)'s
  `docs/conf.py`, and verified to reproduce its output; see
  [docs/validation.md](docs/validation.md).
