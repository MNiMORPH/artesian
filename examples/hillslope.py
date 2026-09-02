"""
A hillslope relaxing under linear diffusion – the smallest useful artesian demo.

Deliberately not GRLP: a self-contained model in a few lines of numpy, so the
example shows the shape of a demo rather than the details of any one model.
Everything artesian needs is here – a Panel app ending in ``.servable()``, and
nothing imported that Pyodide cannot supply.

Build and view it with::

    artesian build examples/hillslope.py -o _artesian_build -r numpy --serve

The physics: elevation z evolves as ∂z/∂t = D ∂²z/∂x² + U, with z held at zero
at both base-level boundaries. The steady form is the parabola
z = U x (L - x) / 2D, so raising uplift grows the ridge and raising diffusivity
rounds it off. Both knobs are live while it runs, and the dashed line shows the
steady form the profile is currently chasing.
"""
import numpy as np
import panel as pn
from bokeh.models import ColumnDataSource
from bokeh.plotting import figure

from artesian.live import animator, reset_button, responsive

pn.extension()

NX = 101                        # nodes across the hillslope
LENGTH = 100.                   # hillslope width [m]
DX = LENGTH / (NX - 1)

# Slider bounds are chosen together with the fixed y-axis: over these ranges the
# steady crest U L² / 8D spans 2.5–62.5 m, which one axis can show without
# rescaling mid-animation.
D_MIN, D_MAX, D0 = 0.01, 0.05, 0.02        # diffusivity [m²/yr]
U_MIN, U_MAX, U0 = 0.1, 0.5, 0.3           # uplift rate [mm/yr]

# Explicit diffusion is stable for dt <= dx²/2D; take half of that at the
# largest D on offer, so the step stays stable wherever the sliders go.
DT = 0.25 * DX ** 2 / D_MAX                # 5 yr

# The slowest diffusive mode takes L²/π²D ≈ 20-100 kyr to relax, which is
# far too many steps to draw one per frame. Advancing 60 per frame brings the
# profile to 95% of its steady crest in 205 frames at D = 0.05 and 1023 at
# D = 0.01 – roughly 7 to 34 s at 30 fps, measured, which is long enough to
# watch and short enough to sit through.
STEPS_PER_FRAME = 60

x = np.linspace(0., LENGTH, NX)

# `sim`, never `state`: panel exports pn.state, and shadowing it fails silently.
sim = {"z": np.zeros(NX), "t": 0.}

D = pn.widgets.FloatSlider(name="Diffusivity  D  [m²/yr]", start=D_MIN,
                           end=D_MAX, step=0.005, value=D0, format="0.000")
U = pn.widgets.FloatSlider(name="Uplift rate  U  [mm/yr]", start=U_MIN,
                           end=U_MAX, step=0.05, value=U0, format="0.00")


def _steady():
    """The parabola balancing uplift against diffusion, for the live sliders."""
    return 1e-3 * U.value / (2. * D.value) * x * (LENGTH - x)


def step():
    """Advance one frame, reading the sliders as live forcing."""
    z = sim["z"]
    d = D.value
    uplift = 1e-3 * U.value                # slider reads mm/yr; model wants m/yr
    for _ in range(STEPS_PER_FRAME):
        z[1:-1] += DT * (d * (z[:-2] - 2. * z[1:-1] + z[2:]) / DX ** 2 + uplift)
        z[0] = z[-1] = 0.                  # fixed base level at both edges
    sim["t"] += STEPS_PER_FRAME * DT
    _redraw()


def _redraw():
    profile.data = {"x": x, "z": sim["z"]}
    steady.data = {"x": x, "z": _steady()}
    fig.title.text = "t = %.0f kyr" % (sim["t"] / 1000.)


def do_reset():
    sim["z"] = np.zeros(NX)
    sim["t"] = 0.
    _redraw()


profile = ColumnDataSource(data={"x": x, "z": sim["z"]})
steady = ColumnDataSource(data={"x": x, "z": _steady()})

# Sized at 680x360, then made to fill whatever container it is embedded in
# while keeping those proportions -- so the hillslope's steepness looks the
# same to every reader. See artesian.live.responsive for why holding the
# ratio matters more than simply filling the width.
fig = figure(height=360, width=680, title="t = 0 kyr",
             x_axis_label="Distance across hillslope [m]",
             y_axis_label="Elevation [m]")
responsive(fig)
fig.line("x", "z", source=steady, line_width=1, line_dash="dashed",
         color="gray", legend_label="steady form")
fig.line("x", "z", source=profile, line_width=3, legend_label="hillslope")
fig.y_range.start, fig.y_range.end = -2., 70.
fig.legend.location = "top_left"

# Redraw the steady curve as soon as a slider moves, so the target updates even
# while the animation is paused.
D.param.watch(lambda event: _redraw(), "value")
U.param.watch(lambda event: _redraw(), "value")

pn.Column(
    pn.pane.Markdown(
        "### A hillslope finding its steady form\n"
        "Press **▶** and drag the sliders while it runs. More **uplift** grows "
        "the ridge; more **diffusivity** rounds it off faster. The dashed line "
        "is the steady parabola for the current settings – the profile chases "
        "it, and catches it when erosion balances uplift."),
    pn.Row(animator(step), reset_button(do_reset, name="Flatten")),
    D, U, fig,
    sizing_mode="stretch_width",   # or the figure has nothing to fill
).servable(title="Hillslope diffusion")
