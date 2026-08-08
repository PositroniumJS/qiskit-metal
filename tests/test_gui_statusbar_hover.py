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

"""Live cursor coordinates in the status bar.

The status bar had a label but effectively nothing wrote to it: the only
writer was ``_report_point_position``, which fires on a *click* and only when
the Coords toggle is enabled. During normal use the bar sat empty, so it was
dead chrome at the bottom of the window.

``_report_hover_position`` now updates it from ``_on_mouse_motion``. That runs
on every motion event, so the implementation must stay cheap -- it only sets
QLabel text and never touches the canvas or forces a redraw. These tests pin
the behaviour and the no-redraw property.

Skips when PySide6 is absent (lite install).
"""

import os
from types import SimpleNamespace

import matplotlib
import pytest

matplotlib.use("Agg")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from qiskit_metal.renderers.renderer_mpl.mpl_interaction import PanAndZoom  # noqa: E402


def motion_event(xdata, ydata):
    """A matplotlib-like motion event carrying only what the handler reads."""
    return SimpleNamespace(
        xdata=xdata, ydata=ydata, button=None, name="motion_notify_event"
    )


@pytest.fixture(name="qapp", scope="module")
def qapp_fixture():
    """A QApplication; Qt requires one before any QWidget."""
    return QApplication.instance() or QApplication([])


@pytest.fixture(name="panzoom")
def panzoom_fixture(qapp):  # pylint: disable=unused-argument
    """A PanAndZoom on a bare figure, wired to a status-bar label."""
    figure = matplotlib.pyplot.figure()
    figure.add_subplot(1, 1, 1)
    panzoom = PanAndZoom(figure)
    panzoom._statusbar_label = QLabel()
    yield panzoom
    matplotlib.pyplot.close(figure)


class TestHoverReadout:
    """The bar reports position without needing a click."""

    def test_reports_coordinates_on_motion(self, panzoom):
        """Plain hover -- no button pressed, no toggle enabled."""
        panzoom._on_mouse_motion(motion_event(1.2345, -0.6789))

        text = panzoom._statusbar_label.text()
        assert "1.2345" in text
        assert "-0.6789" in text

    def test_blank_outside_the_axes(self, panzoom):
        """Off-axes there is no data coordinate, so report nothing."""
        panzoom._on_mouse_motion(motion_event(1.0, 2.0))
        assert panzoom._statusbar_label.text()

        panzoom._on_mouse_motion(motion_event(None, None))
        assert panzoom._statusbar_label.text() == ""

    def test_updates_on_each_move(self, panzoom):
        """The readout tracks the cursor rather than latching."""
        panzoom._on_mouse_motion(motion_event(1.0, 1.0))
        first = panzoom._statusbar_label.text()

        panzoom._on_mouse_motion(motion_event(5.0, 5.0))
        assert panzoom._statusbar_label.text() != first

    def test_no_label_is_harmless(self, panzoom):
        """Headless / no-status-bar callers must not crash on motion."""
        panzoom._statusbar_label = None
        panzoom._on_mouse_motion(motion_event(1.0, 1.0))  # must not raise

    def test_hover_does_not_redraw(self, panzoom, monkeypatch):
        """Motion runs constantly; a redraw per event would be unusable."""
        draws = []
        monkeypatch.setattr(panzoom.figure.canvas, "draw", lambda: draws.append(1))

        for i in range(25):
            panzoom._on_mouse_motion(motion_event(i * 0.1, i * 0.1))

        assert not draws
