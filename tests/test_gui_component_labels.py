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

"""Label-every-component on the plot canvas.

``PlotCanvas.highlight_components`` could already draw a bounding box, the
component name, pin arrows and pin names, but only for a caller-supplied list
and only with pins always on. These tests cover the additions that make it
usable as a "what am I looking at" control:

- ``highlight_all_components`` labels the whole design without the caller
  enumerating it,
- ``show_pins=False`` drops the per-pin arrows and names, which otherwise
  swamp the component names on a dense chip,
- ``clear_highlight`` removes the annotations again.

Driven through ``PlotCanvas`` against a real Matplotlib axis rather than a
constructed ``MetalGUI``, so no display or main window is needed. Skips when
PySide6 is absent (lite install) -- the canvas module imports Qt at top level.
"""

import matplotlib
import pytest

matplotlib.use("Agg")

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from qiskit_metal.designs.design_planar import DesignPlanar  # noqa: E402
from qiskit_metal.qlibrary.qubits.transmon_pocket import TransmonPocket  # noqa: E402
from qiskit_metal.renderers.renderer_mpl.mpl_canvas import PlotCanvas  # noqa: E402

COMPONENT_NAMES = ["Q1", "Q2", "Q3"]
PIN_NAMES = {"a", "b"}


@pytest.fixture(name="design")
def design_fixture():
    """Three transmons, each with two named connection pads."""
    design = DesignPlanar()
    positions = [("-1.5mm", "0mm"), ("1.5mm", "0mm"), ("0mm", "1.5mm")]
    for name, (pos_x, pos_y) in zip(COMPONENT_NAMES, positions):
        TransmonPocket(
            design,
            name,
            options=dict(
                pos_x=pos_x,
                pos_y=pos_y,
                connection_pads=dict(
                    a=dict(loc_W=1, loc_H=1),
                    b=dict(loc_W=-1, loc_H=1),
                ),
            ),
        )
    return design


class _ParentStub(QWidget):
    """Stands in for ``QMainWindowPlot``.

    ``PlotCanvas.__init__`` reads ``parent.gui`` and calls
    ``setParent(parent)``, so this has to be a real QWidget -- but nothing on
    the annotation path needs a populated ``gui``, so we skip building a
    MetalGUI (and its main window) entirely.
    """

    gui = None


@pytest.fixture(name="qapp", scope="module")
def qapp_fixture():
    """A QApplication for the module; Qt requires one before any QWidget.

    The platform is passed as an argument rather than set through
    ``QT_QPA_PLATFORM``. An environment variable set at import time leaks to
    every later test in the run -- including the subprocesses spawned by
    ``test_gui_init``, which then launch under a different platform plugin
    than they intend.
    """
    return QApplication.instance() or QApplication(
        ["qiskit-metal-tests", "-platform", "offscreen"]
    )


@pytest.fixture(name="canvas")
def canvas_fixture(design, qapp):  # pylint: disable=unused-argument
    """A PlotCanvas bound to that design, without a real main window."""
    parent = _ParentStub()
    canvas = PlotCanvas(design, parent=parent)
    yield canvas
    matplotlib.pyplot.close(canvas.figure)
    parent.deleteLater()


def drawn_texts(canvas):
    """Return the set of label strings currently on the canvas."""
    return {artist.get_text() for artist in canvas._annotations["text"]}


class TestHighlightAllComponents:
    """Labelling the whole design in one call."""

    def test_returns_component_count(self, canvas):
        """The count is what the caller reports to the user."""
        assert canvas.highlight_all_components() == len(COMPONENT_NAMES)

    def test_labels_every_component(self, canvas):
        """No component is left unlabelled."""
        canvas.highlight_all_components(show_pins=False)
        assert drawn_texts(canvas) == set(COMPONENT_NAMES)

    def test_draws_bounding_boxes(self, canvas):
        """One box per component, so labels are attributable to a shape."""
        canvas.highlight_all_components(show_pins=False)
        assert len(canvas._annotations["patch"]) == len(COMPONENT_NAMES)


class TestShowPinsToggle:
    """``show_pins`` is the dense-chip escape hatch."""

    def test_pins_included_by_default(self, canvas):
        """Default keeps the previous behaviour: pins are drawn."""
        canvas.highlight_all_components()
        assert PIN_NAMES <= drawn_texts(canvas)

    def test_pins_excluded_when_off(self, canvas):
        """Only component names survive."""
        canvas.highlight_all_components(show_pins=False)
        assert not PIN_NAMES & drawn_texts(canvas)

    def test_pins_off_draws_fewer_artists(self, canvas):
        """Turning pins off must actually reduce clutter, not just rename it."""
        canvas.highlight_all_components(show_pins=True)
        with_pins = len(canvas._annotations["text"]) + len(canvas._annotations["patch"])

        canvas.highlight_all_components(show_pins=False)
        without_pins = len(canvas._annotations["text"]) + len(
            canvas._annotations["patch"]
        )

        assert without_pins < with_pins

    def test_explicit_list_honours_show_pins(self, canvas):
        """The toggle applies to the targeted call too, not only to 'all'."""
        canvas.highlight_components(["Q1"], show_pins=False)
        assert drawn_texts(canvas) == {"Q1"}


class TestClearing:
    """Labels are transient and must be removable."""

    def test_clear_annotation_removes_labels(self, canvas):
        """``clear_annotation`` backs the GUI's Clear-labels action."""
        canvas.highlight_all_components()
        assert drawn_texts(canvas)

        canvas.clear_annotation()
        assert not canvas._annotations["text"]
        assert not canvas._annotations["patch"]

    def test_relabelling_does_not_accumulate(self, canvas):
        """Repeated calls replace rather than stack duplicate labels."""
        canvas.highlight_all_components(show_pins=False)
        first = len(canvas._annotations["text"])

        canvas.highlight_all_components(show_pins=False)
        assert len(canvas._annotations["text"]) == first

    def test_clearing_redraws(self, canvas, monkeypatch):
        """Detaching the artists is not enough -- the canvas must redraw.

        ``highlight_components`` refreshes at the end of its own run, so
        without a refresh here the labels stayed painted on screen and the
        Clear-labels button looked like it did nothing.
        """
        canvas.highlight_all_components()

        draws = []
        monkeypatch.setattr(canvas, "draw", lambda *a, **k: draws.append(1))
        monkeypatch.setattr(canvas, "draw_idle", lambda *a, **k: draws.append(1))

        canvas.clear_annotation()
        canvas.refresh()

        assert draws, "clearing labels must trigger a redraw"
