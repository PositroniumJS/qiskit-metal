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

"""Opening a renderer that is not installed must say so.

Since the lite-by-default flip, ``QDesign._start_renderers`` skips any
renderer whose module or transitive dependency is missing -- that is what lets
``pip install quantum-metal`` work without Ansys or gmsh. The renderer is then
absent from ``design.renderers``, and clicking its toolbar button used to fail
somewhere deeper with a message that never mentioned the real problem.

The check is a dictionary lookup, deliberately not an import: the import was
already attempted when the design was created. Probing by importing here would
undo the lazification the lite install depends on, and probing for a *running*
AEDT would be slow enough to block the UI.
"""

import pytest

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
from qiskit_metal._gui.main_window import (  # noqa: E402
    RENDERER_EXTRAS,
    QMainWindowExtension,
)


class FakeLogger:
    """Captures warnings so tests can assert the problem was logged."""

    def __init__(self):
        self.warnings = []

    def warning(self, msg, *_, **__):
        """Record a warning."""
        self.warnings.append(str(msg))

    def info(self, *_, **__):
        """Ignore."""

    def error(self, *_, **__):
        """Ignore."""


class FakeDesign:
    """Just the ``renderers`` mapping the check consults."""

    def __init__(self, renderers):
        self.renderers = dict.fromkeys(renderers, object())


class FakeWindow:
    """Binds the real methods to a stub, avoiding a full QMainWindow."""

    _renderer_available = QMainWindowExtension._renderer_available
    _warn_if_ansys_unlikely = QMainWindowExtension._warn_if_ansys_unlikely

    def __init__(self, renderers):
        self.design = FakeDesign(renderers)
        self.logger = FakeLogger()
        self.dialogs = []


@pytest.fixture(name="captured_dialogs")
def captured_dialogs_fixture(monkeypatch):
    """Intercept QMessageBox.warning so no window is shown."""
    shown = []
    monkeypatch.setattr(
        "qiskit_metal._gui.main_window.QMessageBox.warning",
        lambda parent, title, text, *a, **k: shown.append((title, text)),
    )
    return shown


class TestAvailableRenderer:
    """A registered renderer opens as before."""

    def test_returns_true(self, captured_dialogs):
        """No interruption when the renderer is present."""
        window = FakeWindow(["hfss", "q3d", "gds"])

        assert window._renderer_available("hfss", "HFSS") is True
        assert not captured_dialogs

    def test_does_not_warn(self, captured_dialogs):  # pylint: disable=unused-argument
        """Nothing to report, so nothing is logged."""
        window = FakeWindow(["gds"])

        window._renderer_available("gds", "GDS")
        assert not window.logger.warnings


class TestMissingRenderer:
    """A skipped renderer must be explained, not silently broken."""

    def test_returns_false(self, captured_dialogs):  # pylint: disable=unused-argument
        """The caller uses this to abort before opening the window."""
        window = FakeWindow(["gds"])

        assert window._renderer_available("hfss", "HFSS") is False

    def test_shows_a_dialog(self, captured_dialogs):
        """The user gets told, not just the log."""
        window = FakeWindow(["gds"])

        window._renderer_available("hfss", "HFSS")

        assert len(captured_dialogs) == 1
        title, _ = captured_dialogs[0]
        assert "HFSS" in title

    def test_message_names_the_install_extra(self, captured_dialogs):
        """A message that does not say how to fix it is not much use."""
        window = FakeWindow(["gds"])

        window._renderer_available("hfss", "HFSS")

        _, text = captured_dialogs[0]
        assert "quantum-metal[ansys]" in text

    def test_mesh_renderers_point_at_the_mesh_extra(self, captured_dialogs):
        """gmsh/Elmer come from a different extra than Ansys."""
        window = FakeWindow([])

        window._renderer_available("gmsh", "Gmsh")

        _, text = captured_dialogs[0]
        assert "quantum-metal[mesh]" in text

    def test_unknown_renderer_falls_back_to_full(self, captured_dialogs):
        """An unmapped key still yields actionable advice."""
        window = FakeWindow([])

        window._renderer_available("something_new", "Something")

        _, text = captured_dialogs[0]
        assert "quantum-metal[full]" in text

    def test_logs_the_reason(self, captured_dialogs):  # pylint: disable=unused-argument
        """Leaves a trace for a bug report, not only a transient dialog."""
        window = FakeWindow(["gds"])

        window._renderer_available("hfss", "HFSS")

        assert any("hfss" in w for w in window.logger.warnings)


class TestAnsysPlatformNote:
    """Registering the Python side says nothing about AEDT being installed."""

    def test_warns_off_windows(self, monkeypatch, captured_dialogs):
        """AEDT is Windows-only; the window opens but cannot connect."""
        monkeypatch.setattr("qiskit_metal._gui.main_window.os.name", "posix")
        window = FakeWindow(["hfss"])

        window._warn_if_ansys_unlikely("HFSS")

        assert window.logger.warnings
        assert "AEDT" in window.logger.warnings[0]

    def test_silent_on_windows(self, monkeypatch, captured_dialogs):
        """Where AEDT can actually run, say nothing."""
        monkeypatch.setattr("qiskit_metal._gui.main_window.os.name", "nt")
        window = FakeWindow(["hfss"])

        window._warn_if_ansys_unlikely("HFSS")

        assert not window.logger.warnings
        assert not captured_dialogs

    def test_pops_a_dialog_too(self, monkeypatch, captured_dialogs):
        """The log dock is hidden by default; a passive log line alone was
        easy to miss until AEDT connection failed later with no obvious
        cause."""
        monkeypatch.setattr("qiskit_metal._gui.main_window.os.name", "posix")
        window = FakeWindow(["hfss"])

        window._warn_if_ansys_unlikely("HFSS")

        assert len(captured_dialogs) == 1
        title, text = captured_dialogs[0]
        assert "HFSS" in title
        assert "AEDT" in text

    def test_dialog_shown_once_per_label(self, monkeypatch, captured_dialogs):
        """Repeat clicks (opening/closing the same renderer window) must
        not repeat the same modal every time -- only the first is useful."""
        monkeypatch.setattr("qiskit_metal._gui.main_window.os.name", "posix")
        window = FakeWindow(["hfss", "q3d"])

        window._warn_if_ansys_unlikely("HFSS")
        window._warn_if_ansys_unlikely("HFSS")
        window._warn_if_ansys_unlikely("HFSS")

        assert len(captured_dialogs) == 1

    def test_dialog_shown_once_per_distinct_label(self, monkeypatch, captured_dialogs):
        """HFSS and Q3D are independent renderers -- each earns its own
        first warning."""
        monkeypatch.setattr("qiskit_metal._gui.main_window.os.name", "posix")
        window = FakeWindow(["hfss", "q3d"])

        window._warn_if_ansys_unlikely("HFSS")
        window._warn_if_ansys_unlikely("Q3D")

        assert len(captured_dialogs) == 2


class TestExtrasMapping:
    """The mapping backs the message, so it has to stay honest."""

    def test_ansys_renderers_map_to_ansys(self):
        """All four Ansys-family renderers come from one extra."""
        for key in ("hfss", "q3d", "aedt_hfss", "aedt_q3d"):
            assert RENDERER_EXTRAS[key] == "ansys"

    def test_open_fem_renderers_map_to_mesh(self):
        """gmsh and Elmer are the open-FEM path."""
        for key in ("gmsh", "elmer"):
            assert RENDERER_EXTRAS[key] == "mesh"

    def test_gds_is_not_listed(self):
        """GDS ships in the base install, so it needs no extra."""
        assert "gds" not in RENDERER_EXTRAS
