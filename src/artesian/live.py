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

__all__ = ["animator", "reset_button", "PLAY_LABEL", "PAUSE_LABEL"]

PLAY_LABEL = "▶ Run"
PAUSE_LABEL = "⏸ Pause"

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
