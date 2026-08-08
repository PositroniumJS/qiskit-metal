# This code is part of Qiskit.
#
# (C) Copyright IBM 2017, 2021.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""View-state preservation across a replot in ``PlotCanvas.plot``.

Editing a component option in ``MetalGUI`` runs
``rebuild -> refresh -> refresh_plot -> PlotWindow.replot -> PlotCanvas.plot``.
That path must not move the camera: the user's zoom/pan has to survive the
replot.

``plot`` saves the limits, lets ``clear_axis`` + ``_plot`` re-autoscale to the
new geometry, then restores the saved limits. The ordering against ``draw`` is
load-bearing and was wrong:

    draw()                 <- renders the buffer from the AUTOSCALED limits
    ax.set_xlim(saved)     <- axes corrected, but nothing redraws the buffer

so the visible canvas showed the autoscaled view while the axes held the
restored one. The user saw the view jump on Enter, then snap back on the next
interaction-driven redraw (the first click of a drag). Restoring before
``draw`` keeps buffer and axes in agreement.

The second regression here: ``prep`` (which captures the limits) originally
ran only inside the ``with_try`` branch, while ``final`` restored on both — so
``with_try=False`` replayed whatever view the *previous* plot had saved.

These tests drive the real ``PlotCanvas.plot`` against a stub ``self`` holding a
real Matplotlib axis, so the ordering is exercised without constructing a
QMainWindow or needing a display.
"""

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
from qiskit_metal.renderers.renderer_mpl.mpl_canvas import PlotCanvas  # noqa: E402

USER_XLIM = (0.20, 0.30)
USER_YLIM = (0.40, 0.50)


class CanvasStub:
    """Minimal stand-in exposing everything ``PlotCanvas.plot`` touches.

    ``draw`` records the limits in force when it is called -- i.e. what the
    rendered buffer would actually show.
    """

    def __init__(self):
        self.figure, self.ax = plt.subplots()
        self.ax.plot([0, 1], [0, 1])
        self._state = {}
        self.mpl_context = {}
        self.logger = logging_stub()
        self.drawn_limits = []

    # --- collaborators used by plot() -------------------------------------
    def hide(self):
        """No-op: Qt widget visibility."""

    def show(self):
        """No-op: Qt widget visibility."""

    def _force_clear_annotations(self):
        """No-op: annotation bookkeeping."""

    def _invalidate_pick_index(self):
        """No-op: click-to-select drops its cached hit-test index here."""

    def get_axis(self):
        """Return the single axis under test."""
        return self.ax

    def clear_axis(self, ax):
        """Mirror the real clear: resets limits and re-enables autoscale."""
        ax.clear()

    def _plot(self, ax):
        """Stand in for rendering geometry that autoscales wider than the user view."""
        ax.plot([0, 10], [0, 10])

    def _watermark_axis(self, ax):
        """No-op: watermark."""

    def draw(self):
        """Record what the buffer would render with."""
        self.drawn_limits.append((self.ax.get_xlim(), self.ax.get_ylim()))


def logging_stub():
    """Return an object absorbing the logger calls ``plot`` may make."""

    class _Logger:
        def error(self, *args, **kwargs):
            """Swallow."""

        def debug(self, *args, **kwargs):
            """Swallow."""

        def warning(self, *args, **kwargs):
            """Swallow."""

    return _Logger()


@pytest.fixture(name="canvas")
def canvas_fixture():
    """A stub canvas zoomed to the user's view, cleaned up after the test."""
    stub = CanvasStub()
    stub.ax.set_xlim(USER_XLIM)
    stub.ax.set_ylim(USER_YLIM)
    yield stub
    plt.close(stub.figure)


def approx_lim(limits):
    """Round a limit pair so float noise doesn't fail an equality check."""
    return (round(limits[0], 6), round(limits[1], 6))


@pytest.mark.parametrize("with_try", [True, False], ids=["with_try", "no_try"])
class TestReplotPreservesView:
    """The camera must not move across a replot, on either code path."""

    def test_axes_limits_restored(self, canvas, with_try):
        """The user's zoom survives clear + re-autoscale."""
        PlotCanvas.plot(canvas, with_try=with_try)

        assert approx_lim(canvas.ax.get_xlim()) == approx_lim(USER_XLIM)
        assert approx_lim(canvas.ax.get_ylim()) == approx_lim(USER_YLIM)

    def test_buffer_drawn_with_restored_limits(self, canvas, with_try):
        """The regression: draw() must run *after* the limits are restored.

        Otherwise the visible canvas and the axes disagree, which is what made
        the view jump and then snap back on the next redraw.
        """
        PlotCanvas.plot(canvas, with_try=with_try)

        assert canvas.drawn_limits, "draw() was never called"
        drawn_x, drawn_y = canvas.drawn_limits[-1]
        assert approx_lim(drawn_x) == approx_lim(USER_XLIM)
        assert approx_lim(drawn_y) == approx_lim(USER_YLIM)

    def test_drawn_state_matches_axes_state(self, canvas, with_try):
        """What was rendered and what the axes hold must agree."""
        PlotCanvas.plot(canvas, with_try=with_try)

        drawn_x, drawn_y = canvas.drawn_limits[-1]
        assert approx_lim(drawn_x) == approx_lim(canvas.ax.get_xlim())
        assert approx_lim(drawn_y) == approx_lim(canvas.ax.get_ylim())


class TestStateCapturedOnEveryPath:
    """``prep`` must run regardless of ``with_try``."""

    def test_no_try_does_not_replay_previous_view(self, canvas):
        """``with_try=False`` originally skipped prep and replayed stale state."""
        # First replot at the user's view populates _state.
        PlotCanvas.plot(canvas, with_try=True)

        # User now zooms somewhere else entirely.
        second_xlim, second_ylim = (5.0, 6.0), (7.0, 8.0)
        canvas.ax.set_xlim(second_xlim)
        canvas.ax.set_ylim(second_ylim)

        PlotCanvas.plot(canvas, with_try=False)

        assert approx_lim(canvas.ax.get_xlim()) == approx_lim(second_xlim)
        assert approx_lim(canvas.ax.get_ylim()) == approx_lim(second_ylim)

    def test_first_plot_without_saved_state_does_not_raise(self):
        """A fresh canvas has an empty ``_state``; plot must still draw."""
        stub = CanvasStub()
        try:
            PlotCanvas.plot(stub, with_try=False)
            assert stub.drawn_limits, "draw() was never called"
        finally:
            plt.close(stub.figure)
