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

"""Shift a length option by a distance, keeping the user's unit.

Positions are stored as unit-bearing strings -- ``'0.5mm'``, ``'500um'``,
``'0.5 mm'`` -- not floats. A nudge produces a displacement in mm, so writing
the result back naively would rewrite every position in millimetres and
quietly reformat options the user wrote deliberately. A design authored in
microns should stay in microns.

Kept free of Qt so the arithmetic can be tested on its own; the GUI only
supplies the displacement.
"""

import re

#: ``-1.25 um`` -> sign+digits, then an optional unit. The unit may be
#: separated by whitespace, and may be absent entirely (a bare number, which
#: Metal treats as millimetres).
_LENGTH_RE = re.compile(r"^\s*([+-]?[\d.]+(?:[eE][+-]?\d+)?)\s*([a-zA-Z]*)\s*$")


def split_length(value) -> tuple:
    """Split a length into its magnitude, unit, and whether a space was used.

    Args:
        value: A length string such as ``'0.5mm'``, or a number.

    Returns:
        tuple: ``(magnitude, unit, spaced)``, or None if it does not look
        like a simple length. ``unit`` is ``''`` for a bare number.
    """
    if isinstance(value, (int, float)):
        return float(value), "", False

    if not isinstance(value, str):
        return None

    match = _LENGTH_RE.match(value)
    if not match:
        return None

    magnitude, unit = match.groups()
    try:
        magnitude = float(magnitude)
    except ValueError:  # pragma: no cover — the regex already constrains this
        return None

    spaced = bool(re.search(r"\d\s+[a-zA-Z]", value))
    return magnitude, unit, spaced


def format_length(magnitude: float, unit: str, spaced: bool, decimals: int = 6) -> str:
    """Render a magnitude back into the shape it came from.

    Args:
        magnitude (float): The new magnitude, in ``unit``.
        unit (str): Unit suffix, possibly empty.
        spaced (bool): Whether the original separated value and unit.
        decimals (int): Maximum decimal places.

    Returns:
        str: e.g. ``'0.55mm'``.
    """
    # ``round`` first so 0.1+0.2 does not render as 0.30000000000000004, then
    # normalize away the trailing zeros round() leaves behind.
    text = f"{round(magnitude, decimals):.{decimals}f}".rstrip("0").rstrip(".")
    if text in ("", "-"):
        text = "0"
    if not unit:
        return text
    return f"{text} {unit}" if spaced else f"{text}{unit}"


def offset_length(value, delta_mm: float, parse_value, decimals: int = 6):
    """Return ``value`` shifted by ``delta_mm``, expressed in its own unit.

    Args:
        value: The current option, e.g. ``'500um'``.
        delta_mm (float): Displacement in millimetres.
        parse_value (callable): ``design.parse_value``; used to learn how many
            millimetres one of ``value``'s units is worth, rather than
            hardcoding a unit table that could drift from Metal's own.
        decimals (int): Maximum decimal places in the result.

    Returns:
        str: The new value, or None if ``value`` is not a simple length.
    """
    parts = split_length(value)
    if parts is None:
        return None
    magnitude, unit, spaced = parts

    mm_per_unit = 1.0
    if unit:
        try:
            mm_per_unit = float(parse_value(f"1{unit}"))
        except Exception:  # pragma: no cover — unknown unit
            return None
        if not mm_per_unit:
            return None

    return format_length(magnitude + delta_mm / mm_per_unit, unit, spaced, decimals)
