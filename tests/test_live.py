"""The responsive() helper: which sizing mode, and what it infers."""

import pytest
from bokeh.plotting import figure

from artesian.live import DEFAULT_MAX_WIDTH, responsive


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
