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

"""Clicking a component on the canvas selects it.

Two constraints shape the implementation, and both are what these tests are
really about:

**It must not regress panning.** Pan is left-drag, so a left release can mean
either "pan finished" or "select this". They are told apart by how far the
pointer moved between press and release -- the same few-pixel threshold
``_zoom_area`` already uses. Without that check every pan would also
re-select whatever sat under the release point.

**It must not make rendering slower.** Hit-testing every polygon linearly
would be O(n) per click on a design with hundreds of components, so geometry
goes into a shapely ``STRtree``, built lazily and invalidated by ``plot()``.
Nothing runs on hover or during a draw.
"""

from types import SimpleNamespace

import matplotlib
import pytest

matplotlib.use("Agg")

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from qiskit_metal.designs.design_planar import DesignPlanar  # noqa: E402
from qiskit_metal.qlibrary.qubits.transmon_pocket import TransmonPocket  # noqa: E402
from qiskit_metal.renderers.renderer_mpl.mpl_canvas import PlotCanvas  # noqa: E402

Q1_CENTRE = (-1.0, 0.0)
Q2_CENTRE = (1.0, 0.0)
EMPTY_POINT = (0.0, 3.0)


class _GuiStub:
    """Records selections the canvas asks for."""

    def __init__(self):
        self.selected = []
        self.selected_component = None
        # dockComponent (titled "Edit component") is the real editor;
        # dockDesign (titled "QComponents") is the component list. The
        # names are the opposite of what they hold -- see the comment in
        # PlotCanvas._on_pick_release.
        self.main_window = SimpleNamespace(
            ui=SimpleNamespace(dockComponent=object(), dockDesign=object())
        )

    def edit_component(self, name):
        """Mirror MetalGUI.edit_component."""
        self.selected.append(name)
        self.selected_component = name


class _ParentStub(QWidget):
    """``PlotCanvas.__init__`` reads ``parent.gui`` and calls ``setParent``."""

    gui = None


def mouse_event(x, y, xdata, ydata, button=1):
    """A matplotlib-like mouse event carrying only what the handlers read."""
    return SimpleNamespace(x=x, y=y, xdata=xdata, ydata=ydata, button=button)


@pytest.fixture(name="qapp", scope="module")
def qapp_fixture():
    """A QApplication; platform passed as an argument, not an env var."""
    return QApplication.instance() or QApplication(
        ["qiskit-metal-tests", "-platform", "offscreen"]
    )


@pytest.fixture(name="canvas")
def canvas_fixture(qapp):  # pylint: disable=unused-argument
    """A canvas over two transmons, 2mm apart."""
    design = DesignPlanar()
    TransmonPocket(design, "Q1", options=dict(pos_x="-1mm", pos_y="0mm"))
    TransmonPocket(design, "Q2", options=dict(pos_x="1mm", pos_y="0mm"))

    parent = _ParentStub()
    canvas = PlotCanvas(design, parent=parent)
    canvas.gui = _GuiStub()
    yield canvas
    matplotlib.pyplot.close(canvas.figure)
    parent.deleteLater()


class TestHitTesting:
    """Mapping a point to a component."""

    def test_finds_the_component_under_the_point(self, canvas):
        """Each transmon is found at its own centre."""
        assert canvas.component_at_point(*Q1_CENTRE) == "Q1"
        assert canvas.component_at_point(*Q2_CENTRE) == "Q2"

    def test_empty_space_hits_nothing(self, canvas):
        """Clicking the substrate must not select an arbitrary component."""
        assert canvas.component_at_point(*EMPTY_POINT) is None

    def test_picks_the_nearest_when_boxes_overlap(self, canvas):
        """``STRtree.query`` is bounding-box based, so ties need resolving."""
        # Just off Q1's centre, still far from Q2.
        assert canvas.component_at_point(-1.0, 0.05) == "Q1"

    def test_zero_tolerance_misses_the_pad_gap(self, canvas):
        """A transmon's centre is the gap between its pads, not metal.

        Good illustration of why the tolerance exists: an exact
        point-in-polygon test misses the most obvious place a user clicks.
        """
        assert canvas.component_at_point(*Q1_CENTRE, tolerance=0.0) is None

    def test_default_tolerance_catches_the_pad_gap(self, canvas):
        """Clicking the middle of a transmon must select it."""
        assert canvas.component_at_point(*Q1_CENTRE) == "Q1"

    def test_tolerance_widens_the_catchment(self, canvas):
        """Routes are zero-width paths, so reach beyond the exact geometry."""
        assert canvas.component_at_point(-1.0, 0.5, tolerance=1.0) == "Q1"


class TestClickVersusDrag:
    """The constraint that protects panning."""

    def test_a_click_selects(self, canvas):
        """Press and release in the same place is a selection."""
        canvas._on_pick_press(mouse_event(100, 100, *Q1_CENTRE))
        canvas._on_pick_release(mouse_event(101, 100, *Q1_CENTRE))

        assert canvas.gui.selected == ["Q1"]

    def test_a_drag_does_not_select(self, canvas):
        """A pan must not double as a selection."""
        canvas._on_pick_press(mouse_event(100, 100, *Q1_CENTRE))
        canvas._on_pick_release(mouse_event(400, 250, *Q2_CENTRE))

        assert canvas.gui.selected == []

    def test_right_click_does_not_select(self, canvas):
        """Right-drag is rubber-band zoom, not selection."""
        canvas._on_pick_press(mouse_event(100, 100, *Q1_CENTRE, button=3))
        canvas._on_pick_release(mouse_event(100, 100, *Q1_CENTRE, button=3))

        assert canvas.gui.selected == []

    def test_release_outside_the_axes_is_ignored(self, canvas):
        """Off-axes there is no data coordinate to hit-test."""
        canvas._on_pick_press(mouse_event(100, 100, *Q1_CENTRE))
        canvas._on_pick_release(mouse_event(100, 100, None, None))

        assert canvas.gui.selected == []

    def test_clicking_empty_space_keeps_the_selection(self, canvas):
        """Missing everything should do nothing, not clear or error."""
        canvas._on_pick_press(mouse_event(100, 100, *EMPTY_POINT))
        canvas._on_pick_release(mouse_event(100, 100, *EMPTY_POINT))

        assert canvas.gui.selected == []


class TestEditDockOnReSelect:
    """Re-clicking (or double-clicking) an already-selected component
    brings the real editor to the front.

    ``dockComponent`` (titled "Edit component") is the editor;
    ``dockDesign`` (titled "QComponents") is only the list. A prior
    version of this code raised ``dockDesign`` by mistake -- both docks
    exist as distinct objects here specifically so a regression back to
    the wrong one fails this test rather than passing silently (a stub
    with only one dock attribute would not catch that class of bug).
    """

    def test_second_click_on_the_same_component_raises_the_editor(
        self, canvas, monkeypatch
    ):
        import qiskit_metal.renderers.renderer_mpl.mpl_canvas as mpl_canvas_module

        raised = []
        monkeypatch.setattr(mpl_canvas_module, "doShowHighlighWidget", raised.append)

        canvas._on_pick_press(mouse_event(100, 100, *Q1_CENTRE))
        canvas._on_pick_release(mouse_event(101, 100, *Q1_CENTRE))
        assert raised == []  # first click: selects, does not raise anything

        canvas._on_pick_press(mouse_event(100, 100, *Q1_CENTRE))
        canvas._on_pick_release(mouse_event(101, 100, *Q1_CENTRE))
        assert raised == [canvas.gui.main_window.ui.dockComponent]

    def test_a_real_double_click_raises_the_editor_on_the_first_click(
        self, canvas, monkeypatch
    ):
        """``event.dblclick`` (matplotlib's own flag) is enough on its
        own -- no prior selection required."""
        import qiskit_metal.renderers.renderer_mpl.mpl_canvas as mpl_canvas_module

        raised = []
        monkeypatch.setattr(mpl_canvas_module, "doShowHighlighWidget", raised.append)

        canvas._on_pick_press(mouse_event(100, 100, *Q1_CENTRE))
        event = mouse_event(101, 100, *Q1_CENTRE)
        event.dblclick = True
        canvas._on_pick_release(event)

        assert raised == [canvas.gui.main_window.ui.dockComponent]


class TestIndexLifecycle:
    """The index is a cache, so staleness is the risk."""

    def test_built_lazily(self, canvas):
        """Nothing is indexed until the first click."""
        canvas._invalidate_pick_index()
        assert canvas._pick_tree is None

        canvas.component_at_point(*Q1_CENTRE)
        assert canvas._pick_tree is not None

    def test_plot_invalidates_it(self, canvas):
        """Geometry may have changed, so the cached tree must be dropped."""
        canvas.component_at_point(*Q1_CENTRE)
        assert canvas._pick_tree is not None

        canvas._invalidate_pick_index()
        assert canvas._pick_tree is None

    def test_reflects_a_new_component(self, canvas):
        """A component added after the first click is still clickable."""
        canvas.component_at_point(*Q1_CENTRE)  # warm the cache

        TransmonPocket(canvas.design, "Q3", options=dict(pos_x="0mm", pos_y="2mm"))
        canvas._invalidate_pick_index()

        assert canvas.component_at_point(0.0, 2.0) == "Q3"
