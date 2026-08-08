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
