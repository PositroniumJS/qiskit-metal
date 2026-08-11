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

"""Version comparison behind the persisted-state guard.

``restore_window_settings`` discards window state written by an older Metal.
That is one of the five issue-#1048 defenses, and it is also what gives users
new layout defaults on upgrade rather than a stale saved arrangement.

The comparison was ``__version__ > version_settings`` -- a plain string
compare, correct only while every version component stays single-digit.
``'0.10.0' > '0.9.0'`` is False, so from v0.10.0 the guard would have stopped
firing silently: no error, no symptom, just a crash defense quietly switched
off and old layouts restored into a newer GUI.

Any doubt resolves to "newer", because discarding state that might have been
fine is the cheap failure and restoring state that is not is the expensive
one.
"""

import pytest

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
from qiskit_metal._gui.main_window_base import _is_newer_version  # noqa: E402


class TestOrdinaryUpgrades:
    """The cases that already worked."""

    @pytest.mark.parametrize(
        "current,saved",
        [("0.8.0", "0.7.4"), ("0.9.0", "0.8.0"), ("1.0.0", "0.9.0")],
    )
    def test_newer_clears(self, current, saved):
        """A newer release must discard the older release's layout."""
        assert _is_newer_version(current, saved) is True


class TestDoubleDigitBoundary:
    """The regression: string ordering breaks at ten."""

    def test_ten_is_newer_than_nine(self):
        """``'0.10.0' > '0.9.0'`` is False as strings, True as versions."""
        assert _is_newer_version("0.10.0", "0.9.0") is True

    def test_ten_is_newer_than_two(self):
        """The same trap one digit earlier."""
        assert _is_newer_version("0.10.0", "0.2.0") is True

    def test_double_digit_minor_and_patch(self):
        """Patch components have the same problem."""
        assert _is_newer_version("0.8.10", "0.8.9") is True


class TestNoClearWhenNotNewer:
    """Clearing every launch would throw away layouts people arranged."""

    def test_same_version_keeps_state(self):
        """The common case: relaunching the same build."""
        assert _is_newer_version("0.8.0", "0.8.0") is False

    def test_older_running_version_keeps_state(self):
        """Downgrades are unusual; do not silently wipe on one."""
        assert _is_newer_version("0.8.0", "0.9.0") is False


class TestUnparseableValues:
    """A hand-edited registry or a dev build must not crash startup."""

    def test_default_zero_is_older(self):
        """``'0'`` is the default when nothing was ever saved."""
        assert _is_newer_version("0.8.0", "0") is True

    def test_garbage_saved_value_clears(self):
        """Unreadable state is exactly what should be discarded."""
        assert _is_newer_version("0.8.0", "not-a-version") is True

    def test_identical_garbage_is_not_newer(self):
        """Same unparseable string both sides: nothing changed."""
        assert _is_newer_version("dev-build", "dev-build") is False

    def test_never_raises(self):
        """This runs during startup; an exception here breaks the GUI."""
        for current, saved in [
            (None, "0.8.0"),
            ("0.8.0", None),
            ("", ""),
            (0.8, "0.7"),
        ]:
            _is_newer_version(current, saved)  # must not raise
