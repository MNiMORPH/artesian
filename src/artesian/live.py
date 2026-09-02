"""
The small amount of Panel boilerplate every live-model demo rewrites.

Deliberately thin. There is no model abstraction here and no plotting
abstraction: what a demo should draw, and how it should step, differ enough
between models that a shared contract written from one model would fit the
next one badly. What genuinely repeats is the play/pause timer and the reset
button, so that is all this module provides. Build the figure with bokeh (or
whatever you like) yourself.

One trap worth stating, because it costs an afternoon: do **not** name the dict
holding your evolving model ``state``. Panel exports ``pn.state``, and the
shadowing failure is silent and confusing. ``sim`` is a safe habit.

Typical use::

    sim = {"model": make_model(), "t": 0.}

    def step():
        sim["model"].advance(dt)
        source.data = {"x": sim["model"].x, "y": sim["model"].y}

    run = animator(step)                  # a ready-made play/pause toggle
    reset = reset_button(do_reset)
    pn.Column(pn.Row(run, reset), slider, fig).servable()
"""

import panel as pn

__all__ = ["animator", "reset_button", "responsive",
           "PLAY_LABEL", "PAUSE_LABEL", "DEFAULT_MAX_WIDTH"]

PLAY_LABEL = "▶ Run"
PAUSE_LABEL = "⏸ Pause"

#: Widest a responsive figure is allowed to become. Preserving a figure's
#: shape without a bound makes it absurdly tall on a very wide screen: a
#: 680x380 plot scaled to a 2400 px container is 1342 px tall.
DEFAULT_MAX_WIDTH = 1200

#: ~30 fps. The frame budget is the real constraint on this whole approach: a
#: model whose step costs much more than this cannot be animated smoothly, and
#: wants recompute-on-change instead of a timer.
DEFAULT_PERIOD = 33


def animator(step, period=DEFAULT_PERIOD, label=PLAY_LABEL,
             running_label=PAUSE_LABEL, **kwargs):
    """A play/pause toggle wired to a periodic callback.

    ``step`` is called every ``period`` milliseconds while the toggle is on,
    with no arguments. The toggle's own label switches between ``label`` and
    ``running_label`` so one button carries both states.

    Returns the toggle widget; the underlying periodic callback is available
    as ``toggle.callback`` if you need to change the period later.
    """
    toggle = pn.widgets.Toggle(name=label, value=False, **kwargs)
    # Panel hands the periodic callback no arguments; accept and drop any, so
    # a `step(event)` written for a widget watcher also works here.
    ticker = pn.state.add_periodic_callback(lambda *a: step(), period=period,
                                            start=False)

    def _toggled(event):
        if event.new:
            ticker.start()
            toggle.name = running_label
        else:
            ticker.stop()
            toggle.name = label

    toggle.param.watch(_toggled, "value")
    toggle.callback = ticker
    return toggle


def reset_button(on_reset, name="Reset", button_type="primary", **kwargs):
    """A button that calls ``on_reset()`` when clicked.

    ``on_reset`` is called with no arguments; a callback that takes the click
    event still works.
    """
    button = pn.widgets.Button(name=name, button_type=button_type, **kwargs)
    button.on_click(lambda *a: on_reset())
    return button


def responsive(fig, aspect_ratio=None, max_width=DEFAULT_MAX_WIDTH):
    """Let ``fig`` fill its container without changing shape.

    An embedded demo lands in containers you do not control -- a documentation
    page, a course page, a projected slide, a phone -- so a figure fixed at
    some pixel width is wrong nearly everywhere. The fix has a trap in it, and
    this function exists to encode which way out is right rather than leave
    everyone to find it again.

    The tempting mode is ``stretch_width``: it fills the width, but pins the
    height, so the aspect ratio drifts with the window. For anything whose
    meaning lives in a *slope* -- a river's long profile, a hillslope, a
    time series of rates -- that silently changes what the reader sees. A
    680x380 plot has a ratio of 1.79 as drawn, 2.89 in a 1100 px column and
    4.21 in a 1600 px one: the same data, looking three times gentler.

    ``scale_width`` instead scales both dimensions, holding the ratio and so
    holding the vertical exaggeration constant for every reader. Left
    unbounded that overshoots the other way, hence ``max_width``.

    Parameters
    ----------
    fig : bokeh figure
        Modified in place, and returned for convenience.
    aspect_ratio : float, optional
        Width divided by height. Defaults to the figure's current proportions,
        so a figure you have already sized keeps the shape you gave it. Be
        aware that bokeh gives a figure 600x600 when you do not size it, so an
        unsized figure infers 1.0 -- a square, from a default rather than from
        anything you decided. Pass this explicitly if you have not set a width
        and height.
    max_width : int, optional
        Widest the figure may grow. Its greatest height is this over the
        aspect ratio.

    Notes
    -----
    A figure that stretches inside a container that does not is no better off,
    so give the enclosing ``pn.Column`` (or Row) ``sizing_mode="stretch_width"``
    as well.
    """
    if aspect_ratio is None:
        if not fig.width or not fig.height:
            raise ValueError(
                "aspect_ratio must be given for a figure without an explicit "
                "width and height, since there are no current proportions to "
                "preserve")
        aspect_ratio = float(fig.width) / float(fig.height)
    fig.sizing_mode = "scale_width"
    fig.aspect_ratio = aspect_ratio
    fig.max_width = max_width
    return fig
