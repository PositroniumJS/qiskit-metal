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

"""Moving a component with the arrow keys.

Positions are unit-bearing strings (``'0.5mm'``, ``'500um'``), not floats,
while a nudge is a displacement in millimetres. Writing the result back
naively would rewrite every position in mm and quietly reformat options the
author wrote deliberately -- a design in microns must stay in microns. That
conversion is what most of these tests cover.

The other property that matters: a nudge must **reverse exactly**. There is no
undo stack, so the opposite arrow is the only way back, and float drift
accumulating over a few presses would leave a design subtly moved.
"""

import matplotlib
import pytest

matplotlib.use("Agg")

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
from qiskit_metal.designs.design_planar import DesignPlanar  # noqa: E402
from qiskit_metal._gui.utility._nudge import (  # noqa: E402
    format_length,
    offset_length,
    split_length,
)


@pytest.fixture(name="parse_value")
def parse_value_fixture():
    """Metal's own unit parser, so the tests use the real conversions."""
    return DesignPlanar().parse_value


class TestSplitLength:
    """Pulling a length apart without losing how it was written."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("0.5mm", (0.5, "mm", False)),
            ("500um", (500.0, "um", False)),
            ("0.5 mm", (0.5, "mm", True)),
            ("-1.25mm", (-1.25, "mm", False)),
            ("2", (2.0, "", False)),
        ],
    )
    def test_splits_magnitude_unit_and_spacing(self, value, expected):
        """Spacing is captured so the value can be rebuilt as written."""
        assert split_length(value) == expected

    def test_accepts_a_bare_number(self):
        """Metal treats a unitless option as millimetres."""
        assert split_length(0.5) == (0.5, "", False)

    @pytest.mark.parametrize("value", ["main", "", "1mm 2mm", None, [1]])
    def test_rejects_what_is_not_a_length(self, value):
        """Anything unparseable must be refused, not guessed at."""
        assert split_length(value) is None


class TestFormatLength:
    """Rendering back without float noise."""

    def test_keeps_the_unit_attached(self):
        """``0.55mm``, not ``0.55 mm``, when the original had no space."""
        assert format_length(0.55, "mm", spaced=False) == "0.55mm"

    def test_preserves_a_space(self):
        """A user who wrote ``0.5 mm`` gets ``0.55 mm`` back."""
        assert format_length(0.55, "mm", spaced=True) == "0.55 mm"

    def test_strips_float_noise(self):
        """0.1 + 0.2 must not render as 0.30000000000000004."""
        assert format_length(0.1 + 0.2, "mm", spaced=False) == "0.3mm"

    def test_bare_number_stays_bare(self):
        """No unit in, no unit out."""
        assert format_length(2.05, "", spaced=False) == "2.05"


class TestOffsetLength:
    """The conversion that keeps a design in its own units."""

    def test_millimetres_stay_millimetres(self, parse_value):
        """The simple case."""
        assert offset_length("0.5mm", 0.05, parse_value) == "0.55mm"

    def test_microns_stay_microns(self, parse_value):
        """0.05mm is 50um, so 500um becomes 550um -- not 0.55mm."""
        assert offset_length("500um", 0.05, parse_value) == "550um"

    def test_spacing_survives(self, parse_value):
        """Formatting choices are the author's, not ours to normalise."""
        assert offset_length("0.5 mm", 0.05, parse_value) == "0.55 mm"

    def test_negative_positions_move_correctly(self, parse_value):
        """Sign handling, since positions are often negative."""
        assert offset_length("-1.25mm", 0.05, parse_value) == "-1.2mm"

    def test_bare_number_treated_as_millimetres(self, parse_value):
        """Matches how Metal parses a unitless option."""
        assert offset_length("2", 0.05, parse_value) == "2.05"

    def test_non_length_is_refused(self, parse_value):
        """A string option like a chip name must not be arithmetic'd."""
        assert offset_length("main", 0.05, parse_value) is None

    def test_reverses_exactly(self, parse_value):
        """No undo stack, so the opposite arrow is the only way back."""
        moved = offset_length("500um", 0.05, parse_value)
        assert offset_length(moved, -0.05, parse_value) == "500um"

    def test_repeated_moves_do_not_drift(self, parse_value):
        """Ten presses out and ten back must land exactly where it started."""
        value = "0.5mm"
        for _ in range(10):
            value = offset_length(value, 0.05, parse_value)
        for _ in range(10):
            value = offset_length(value, -0.05, parse_value)
        assert value == "0.5mm"


class TestRealClickAndKeyDelivery:
    """A click then an arrow key, injected as genuine Qt events end to end.

    Everything above tests the pure arithmetic helpers; TestClickVersusDrag
    in test_gui_click_select.py calls _on_pick_release() directly with a
    fake event, bypassing Qt's own dispatch entirely. Neither would have
    caught the actual bug: FigureCanvas (PlotCanvas's base class) owns
    keyPressEvent and never propagates an unhandled key to its parent, so
    a handler that lived on the parent QMainWindowPlot was simply
    unreachable -- selection and focus both worked, but the arrow key
    silently did nothing. Real QTest-injected events go through the same
    Qt dispatch a live user's input does and are the only way to see that.
    """

    def test_click_then_arrow_moves_the_component(self):
        """The exact sequence a user performs: click to select, then an
        arrow key. Both must be genuine Qt events for this to mean
        anything -- see the class docstring."""
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt as QtNS, QPoint
        from qiskit_metal._gui.main_window import MetalGUI
        from qiskit_metal.qlibrary.qubits.transmon_pocket import TransmonPocket

        # MetalGUI directly, not qm.gui(design): the latter branches on
        # QISKIT_METAL_HEADLESS (set for this whole suite run) and returns
        # the headless matplotlib viewer instead, which has no QApplication
        # and no real focus/keyboard dispatch to test.
        design = DesignPlanar()
        gui = MetalGUI(design)
        try:
            gui.main_window.show()
            app = QApplication.instance()
            TransmonPocket(design, "Q1")
            gui.rebuild()
            gui.autoscale()
            for _ in range(20):
                app.processEvents()

            canvas = gui.canvas
            # Start focus somewhere else, matching the real bug report:
            # focus stays on whatever dock last had it until proven
            # otherwise.
            gui.main_window.ui.tableComponents.setFocus()
            for _ in range(10):
                app.processEvents()

            ax = canvas.figure.axes[0]
            disp_x, disp_y = ax.transData.transform((0, 0))
            # matplotlib's transform yields PHYSICAL pixels; Qt mouse
            # events take LOGICAL widget coordinates. On a HiDPI display
            # (macOS Retina, devicePixelRatio 2) the unscaled point lands
            # at twice the correct offset and the pick silently misses --
            # CI's offscreen runners have ratio 1, which hid this.
            dpr = canvas.devicePixelRatioF()
            pos = QPoint(
                int(disp_x / dpr),
                int((canvas.figure.bbox.height - disp_y) / dpr),
            )
            # Retry the click a few times: the very first MetalGUI in a
            # process can miss the first synthetic pick (matplotlib's
            # first paint / font-cache warm-up hasn't completed), which
            # made this test order-dependent -- green inside the full
            # suite, red when the file ran alone.
            for _attempt in range(4):
                QTest.mousePress(canvas, QtNS.LeftButton, QtNS.NoModifier, pos)
                for _ in range(10):
                    app.processEvents()
                QTest.mouseRelease(canvas, QtNS.LeftButton, QtNS.NoModifier, pos)
                for _ in range(20):
                    app.processEvents()
                if gui.selected_component == "Q1":
                    break
                QTest.qWait(150)

            assert gui.selected_component == "Q1"

            # THREE consecutive presses, each sent to whatever widget
            # actually holds focus at that moment -- not just one. The
            # first nudge's refresh() used to hand keyboard focus to the
            # variables table (RightClickView), so arrows worked exactly
            # once and then navigated that table instead ("I'm able to
            # use up, down, left, right keys only once" -- user report).
            # Asserting movement on every press pins the
            # _refocus_canvas() fix.
            for press in range(3):
                before = design.components["Q1"].options.pos_x
                QTest.keyClick(app.focusWidget(), QtNS.Key_Right)
                for _ in range(20):
                    app.processEvents()
                after = design.components["Q1"].options.pos_x
                assert after != before, (
                    f"arrow press {press + 1} did not move the component "
                    f"-- keyboard focus was stolen from the canvas "
                    f"(focus is on "
                    f"{type(app.focusWidget()).__name__})"
                )
        finally:
            gui.main_window.force_close = True
            gui.main_window.close()
