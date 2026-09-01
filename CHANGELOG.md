# Changelog

All notable changes to this project are documented here, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `build_app()`: wheel a local model, self-host the panel/bokeh wheels, run
  `panel convert`, and localize the wheel URLs, in one call.
- `artesian.sphinxext`: a Sphinx extension driven by an `artesian_apps` list,
  so demos rebuild with the documentation. `artesian_skip_build` (or
  `ARTESIAN_SKIP_BUILD=1`) reuses existing output.
- `artesian` command line: `build` (with `--serve`) and `check`.
- `check_requirements()`: report whether each requirement can install in the
  browser, before a build is attempted.
- `artesian.live`: `animator()` and `reset_button()`, the only Panel
  boilerplate every live demo rewrites.
- `examples/hillslope.py`: a complete demo of a model unrelated to the one
  artesian was extracted from.

### Notes

- Extracted from the build hook in [GRLP](https://github.com/MNiMORPH/GRLP)'s
  `docs/conf.py`, and verified to reproduce its output; see
  [docs/validation.md](docs/validation.md).
