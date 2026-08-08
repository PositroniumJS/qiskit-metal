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

"""Autoscale frames the components, not the whole die.

``auto_scale`` called ``ax.autoscale()``, which frames every artist on the
axes. Since v0.8.0 ``QMplRenderer`` draws the die outline, so that included
the chip: a default 9x6mm die around a 0.65mm transmon left the component an
unreadable speck. The tutorials were all written assuming the chip is ignored.

The default is now components-only, with ``include_chip=True`` for the whole
die (bound to Shift+A on the plot toolbar). An empty design still falls back
to framing everything, since there are no component bounds to use.
"""

from pathlib import Path

import matplotlib
import pytest

matplotlib.use("Agg")

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

import qiskit_metal._gui  # noqa: E402

from qiskit_metal.designs.design_planar import DesignPlanar  # noqa: E402
from qiskit_metal.qlibrary.qubits.transmon_pocket import TransmonPocket  # noqa: E402
from qiskit_metal.renderers.renderer_mpl.mpl_canvas import PlotCanvas  # noqa: E402

#: The default die is far larger than a single transmon; that gap is the bug.
CHIP_WIDTH_MM = 9.0
COMPONENT_WIDTH_MM = 0.65


class _GuiStub:
    """The slice of MetalGUI that ``plot()`` reaches for.

    Only the watermark needs anything: ``path_imgs`` to find the logo.
    """

    path_imgs = Path(qiskit_metal._gui.__file__).parent / "_imgs"


class _ParentStub(QWidget):
    """``PlotCanvas.__init__`` reads ``parent.gui`` and calls ``setParent``."""

    gui = _GuiStub()


@pytest.fixture(name="qapp", scope="module")
def qapp_fixture():
    """A QApplication; the platform is an argument, not an env var, so it
    cannot leak into other tests or their subprocesses."""
    return QApplication.instance() or QApplication(
        ["qiskit-metal-tests", "-platform", "offscreen"]
    )


@pytest.fixture(name="design")
def design_fixture():
    """One transmon at the origin on a default 9x6mm die."""
    design = DesignPlanar()
    TransmonPocket(design, "Q1", options=dict(pos_x="0mm", pos_y="0mm"))
    return design


@pytest.fixture(name="canvas")
def canvas_fixture(design, qapp):  # pylint: disable=unused-argument
    """A PlotCanvas over that design, with the geometry actually drawn.

    ``plot()`` matters here: it is what puts the die outline on the axes, and
    the die outline is precisely what made the old ``ax.autoscale()`` frame
    the whole chip. Without plotting, the chip-inclusive path has nothing to
    include and the test would pass for the wrong reason.
    """
    parent = _ParentStub()
    canvas = PlotCanvas(design, parent=parent)
    canvas.plot()
    yield canvas
    matplotlib.pyplot.close(canvas.figure)
    parent.deleteLater()


def x_extent(canvas):
    """Width of the current view in mm."""
    xmin, xmax = canvas.get_axis().get_xlim()
    return xmax - xmin


class TestDefaultFramesComponents:
    """The default must not frame the whole die."""

    def test_view_is_component_sized(self, canvas):
        """Comfortably closer to the component than to the chip."""
        canvas.auto_scale()

        assert x_extent(canvas) < CHIP_WIDTH_MM / 2

    def test_component_is_visible_with_margin(self, canvas):
        """Framed with padding, not clipped to the exact bounds."""
        canvas.auto_scale()

        assert x_extent(canvas) > COMPONENT_WIDTH_MM

    def test_default_is_not_chip_inclusive(self, canvas):
        """The two modes must actually differ, or the flag is decorative."""
        canvas.auto_scale()
        components_only = x_extent(canvas)

        canvas.auto_scale(include_chip=True)
        assert x_extent(canvas) > components_only


class TestIncludeChip:
    """Opting in frames the die."""

    def test_frames_the_whole_chip(self, canvas):
        """Wide enough to hold a 9mm die."""
        canvas.auto_scale(include_chip=True)

        assert x_extent(canvas) >= CHIP_WIDTH_MM * 0.9


class TestEmptyDesign:
    """No components means no component bounds to frame."""

    def test_falls_back_without_raising(self, qapp):  # pylint: disable=unused-argument
        """An empty design must still produce a sane view, not an exception."""
        parent = _ParentStub()
        canvas = PlotCanvas(DesignPlanar(), parent=parent)
        try:
            canvas.auto_scale()  # must not raise
            assert x_extent(canvas) > 0
        finally:
            matplotlib.pyplot.close(canvas.figure)
            parent.deleteLater()


class TestComponentBoundsHelper:
    """``zoom_on_components`` and ``auto_scale`` share this."""

    def test_unknown_names_are_ignored(self, canvas):
        """A stale name from the table must not break framing."""
        assert canvas._component_bounds(["Q1", "does-not-exist"]) is not None

    def test_returns_none_when_nothing_matches(self, canvas):
        """Signals the caller to fall back rather than framing nothing."""
        assert canvas._component_bounds(["does-not-exist"]) is None
