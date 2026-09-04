"""artesian.live: the animation tick, and figure sizing."""

import pytest
from bokeh.plotting import figure

from artesian.live import DEFAULT_MAX_WIDTH, animator, responsive


def test_uses_scale_width_not_stretch_width():
    """stretch_width pins the height, so the aspect ratio -- and on a long
    profile the apparent slope -- drifts with the window."""
    f = responsive(figure(width=680, height=380))
    assert f.sizing_mode == "scale_width"


def test_infers_the_figures_existing_proportions():
    f = responsive(figure(width=680, height=380))
    assert f.aspect_ratio == pytest.approx(680. / 380.)


def test_explicit_aspect_ratio_wins():
    f = responsive(figure(width=680, height=380), aspect_ratio=3.)
    assert f.aspect_ratio == 3.


def test_growth_is_bounded():
    """Unbounded, preserving the ratio makes the figure absurdly tall on a
    wide screen: 680x380 scaled to 2400 px is 1342 px tall."""
    assert responsive(figure(width=680, height=380)).max_width \
        == DEFAULT_MAX_WIDTH
    assert responsive(figure(width=680, height=380), max_width=900).max_width \
        == 900


def test_unsized_figure_must_state_its_ratio():
    with pytest.raises(ValueError, match="aspect_ratio must be given"):
        responsive(figure(width=None, height=None))


def test_bokehs_default_size_is_inferred_as_square():
    """Documenting a sharp edge rather than pretending it is not there: bokeh
    gives an unsized figure 600x600, so inference yields 1.0 from a default
    the user never chose."""
    assert responsive(figure()).aspect_ratio == pytest.approx(1.)


# -- the tick must hand the event loop back ------------------------------

def test_the_tick_is_a_coroutine_so_panel_awaits_it():
    """Panel's _periodic_callback only awaits a callback that is awaitable;
    a plain function is called and returns, adding no suspension point."""
    import inspect
    toggle = animator(lambda: None)
    assert inspect.iscoroutinefunction(toggle.callback.callback)


def test_the_tick_still_calls_a_synchronous_step():
    import asyncio
    calls = []
    toggle = animator(lambda: calls.append(1))
    asyncio.run(toggle.callback.callback())
    assert calls == [1]


def test_an_async_step_is_awaited():
    import asyncio
    calls = []

    async def step():
        calls.append(1)

    toggle = animator(step)
    asyncio.run(toggle.callback.callback())
    assert calls == [1]


def test_a_frame_that_overruns_the_period_still_yields():
    """The bug this guards. Panel's loop yields only when a frame finishes
    inside its period, so an overrunning frame starves the event loop
    completely -- and in the browser that is the worker's onmessage, which
    applies the widget patch. The controls do not slow down, they disconnect.
    """
    import asyncio
    import time

    period = 0.033
    overrun = period * 2

    async def panel_loop(func, frames):        # _async_repeat's shape
        for _ in range(frames):
            start = time.monotonic()
            await func()
            timeout = period - (time.monotonic() - start)
            if timeout > 0:
                await asyncio.sleep(timeout)

    async def drive():
        scheduled = []

        async def competitor():                # stands in for onmessage
            while True:
                scheduled.append(1)
                await asyncio.sleep(0)

        def slow_step():
            end = time.monotonic() + overrun
            while time.monotonic() < end:
                pass

        task = asyncio.ensure_future(competitor())
        toggle = animator(slow_step, period=int(period * 1000))
        await panel_loop(toggle.callback.callback, 3)
        task.cancel()
        return len(scheduled)

    assert asyncio.run(drive()) > 0, \
        "an overrunning frame never returned to the event loop"
