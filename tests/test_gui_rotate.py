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

"""Rotating a component with the ``[``/``]`` keys.

``orientation`` is a bare number (no unit suffix, unlike ``pos_x``/``pos_y``),
so this is simpler than the nudge arithmetic -- the property that matters
here is wraparound: a design authored with an orientation near 360 should
never end up with something like "365" after a rotation.
"""

import pytest

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
from qiskit_metal.designs.design_planar import DesignPlanar  # noqa: E402
from qiskit_metal.qlibrary.qubits.transmon_pocket import TransmonPocket  # noqa: E402
from qiskit_metal._gui.main_window import MetalGUI  # noqa: E402


class FakeLogger:
    """Absorbs log calls so tests can assert on them without a real GUI."""

    def __init__(self):
        self.infos = []
        self.warnings = []

    def info(self, msg, *_, **__):
        """Record an info message."""
        self.infos.append(str(msg))

    def warning(self, msg, *_, **__):
        """Record a warning."""
        self.warnings.append(str(msg))

    def error(self, *_, **__):
        """Ignore."""


class FakeGUI:
    """Binds the real rotate methods to a stub, avoiding a full MetalGUI.

    Exactly the class of test that would have caught the nudge/status-bar
    bugs found this session if it had existed for those -- but for pure
    option-mutation logic like this (no real Qt event dispatch involved),
    a stub is the right tool; there is nothing here a real click/key event
    would exercise differently.
    """

    rotate_component = MetalGUI.rotate_component
    rotate_selected = MetalGUI.rotate_selected

    def __init__(self, design):
        self.design = design
        self.logger = FakeLogger()
        self._selected_component = None
        self.highlighted = []

    @property
    def selected_component(self):
        """Mirrors MetalGUI.selected_component."""
        return self._selected_component

    def refresh(self):
        """No-op: no canvas to redraw."""

    def highlight_components(self, names, show_pins=True):
        """Record what would have been highlighted."""
        self.highlighted.append((names, show_pins))


@pytest.fixture(name="design")
def design_fixture():
    """A design with one component to rotate."""
    design = DesignPlanar()
    TransmonPocket(design, "Q1")
    return design


@pytest.fixture(name="gui")
def gui_fixture(design):
    """A GUI stub over that design."""
    return FakeGUI(design)


class TestRotateComponent:
    """Direct rotation of a named component."""

    def test_rotates_by_the_given_delta(self, gui, design):
        """A plain +90 lands exactly on 90."""
        assert design.components["Q1"].options.orientation == "0.0"

        ok = gui.rotate_component("Q1", 90)

        assert ok is True
        assert design.components["Q1"].options.orientation == "90"

    def test_wraps_past_360(self, gui, design):
        """No orientation should ever read like '365' or '-15'."""
        gui.rotate_component("Q1", 350)
        gui.rotate_component("Q1", 20)

        assert design.components["Q1"].options.orientation == "10"

    def test_negative_delta_rotates_the_other_way(self, gui, design):
        """Clockwise (]) is the mirror of counter-clockwise ([)."""
        gui.rotate_component("Q1", -90)

        assert design.components["Q1"].options.orientation == "270"

    def test_reverses_exactly(self, gui, design):
        """The only way back, so it must land exactly where it started."""
        gui.rotate_component("Q1", 37.5)
        gui.rotate_component("Q1", -37.5)

        assert design.components["Q1"].options.orientation == "0"

    def test_unknown_component_is_refused(self, gui):
        """No such component -- nothing to rotate, no crash."""
        assert gui.rotate_component("NoSuchComponent", 90) is False

    def test_missing_orientation_is_refused(self, gui, design):
        """A component with no orientation option is fixed in place."""
        del design.components["Q1"].options["orientation"]

        assert gui.rotate_component("Q1", 90) is False
        assert gui.logger.infos

    def test_non_numeric_orientation_is_refused(self, gui, design):
        """A hand-edited garbage value must not raise -- just refuse."""
        design.components["Q1"].options.orientation = "not-a-number"

        assert gui.rotate_component("Q1", 90) is False
        assert gui.logger.warnings

    def test_rebuild_triggers_a_highlight(self, gui, design):
        """The rebuild clears the selection outline; re-asserting it is
        what keeps the just-rotated component visibly picked out."""
        gui.rotate_component("Q1", 90)

        assert gui.highlighted == [(["Q1"], False)]


class TestRotateSelected:
    """The keyboard-shortcut entry point: rotate whatever is selected."""

    def test_rotates_the_selected_component(self, gui, design):
        gui._selected_component = "Q1"

        ok = gui.rotate_selected(90)

        assert ok is True
        assert design.components["Q1"].options.orientation == "90"

    def test_nothing_selected_is_refused(self, gui):
        """Matches nudge_selected's behavior for the same situation."""
        assert gui.rotate_selected(90) is False
        assert gui.logger.infos
