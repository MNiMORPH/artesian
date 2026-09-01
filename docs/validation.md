# Validation

## Reproducing the hook artesian was extracted from

`artesian` began as ~40 hand-rolled lines in
[GRLP](https://github.com/MNiMORPH/GRLP)'s `docs/conf.py`, which compiled
`interactive_demo/grlp_panel.py` into the demo published at
<https://grlp.readthedocs.io/en/latest/interactive.html>. The extraction is only
trustworthy if the library reproduces what the hook produced, so that is checked
directly rather than assumed.

Building the same app through `artesian`:

```sh
artesian build GRLP/interactive_demo/grlp_panel.py -o out \
    -p GRLP -r numpy -r scipy -r networkx
```

and diffing the generated `grlp_panel.js` against GRLP's committed
`docs/_static/interactive/grlp_panel.js`, with version numbers normalized
(`sed -E 's/[0-9]+\.[0-9]+\.[0-9]+/VER/g'`, since the two builds pinned
different panel/bokeh releases):

```
diff reference.js artesian.js   ->   no differences
```

The outputs are identical in structure, requirement list, and wheel
localization. The only differences are the pinned versions, which come from the
building environment by design:

| | reference (GRLP conf.py) | artesian |
|---|---|---|
| panel | 1.9.3 | 1.9.4 |
| bokeh | 3.9.1 | 3.9.2 |
| grlp | 2.1.0 | 2.1.0 |

Verified 2026-09-01, `artesian` at commit `HEAD~1`, GRLP branch
`valley-realism`.

## Two findings from that build

Both were found by running the extraction against the real case, and both are
now handled in the library rather than left as folklore.

1. **`panel convert` can fail and still exit 0.** It printed
   `Failed to convert ... does not publish any Panel contents` and returned
   success, so `subprocess.run(check=True)` was satisfied and `build_app`
   returned a path to a file that did not exist. `build_app` now verifies the
   page exists and raises otherwise.

2. **The model must be importable in the *building* environment.**
   `panel convert` executes the app to discover what it serves, so shipping the
   model as a wheel for the browser is not sufficient – it must also be
   installed where the build runs. This is why GRLP's demo builds on Read the
   Docs, which `pip install .`s the package before Sphinx runs. The error
   message for finding 1 states this, since the underlying failure is opaque.
