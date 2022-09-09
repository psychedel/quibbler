from matplotlib import pyplot as plt

from pyquibbler import iquib, undo, redo
from tests.integration.quib.graphics.widgets.utils import count_canvas_draws, count_redraws


def test_drag_right_click_and_undo(create_axes_mouse_press_move_release_event, axes, get_live_artists):

    max_xlim = 20
    axes.set_xlim([0, max_xlim])
    axes.set_ylim([0, 1])

    marker_x = iquib(15)
    plot_quib = axes.plot(marker_x, 0, markerfacecolor='k', marker='^', markersize=30, pickradius=30)

    with count_redraws(plot_quib) as quib_redraw_count, \
            count_canvas_draws(axes.figure.canvas) as canvas_redraw_count:
        create_axes_mouse_press_move_release_events(((15, 0), (10, 0)))
        assert marker_x.get_value() == 10

        create_axes_mouse_press_move_release_events(((10, 0), (5, 0)))
        assert marker_x.get_value() == 5

        create_axes_mouse_press_move_release_events(((5, 0),))

        # right click (reset to default)
        create_axes_mouse_press_move_release_events(((5, 0),))
        assert marker_x.get_value() == 15

        undo()
        assert marker_x.get_value() == 5

        undo()
        assert marker_x.get_value() == 15

    assert canvas_redraw_count.count == 5  # 2 x motion + reset + 2 x undo
    assert quib_redraw_count.count == 5


def test_drag_xy_undo(axes, create_axes_mouse_press_move_release_event, get_live_artists):

    max_lim = 20
    axes.set_xlim(0, max_lim)
    axes.set_ylim(0, max_lim)

    xy = iquib([15, 15])
    x, y = xy
    axes.plot(x, y, markerfacecolor='k', marker='o')

    create_axes_mouse_press_move_release_events(((15, 15), (10, 10), (5, 5)))

    assert xy.get_value() == [5, 5]

    undo()
    assert xy.get_value() == [15, 15]

    redo()
    assert xy.get_value() == [5, 5]
