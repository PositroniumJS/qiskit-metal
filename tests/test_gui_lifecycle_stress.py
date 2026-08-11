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

"""Repeated MetalGUI build/teardown cycles must leave no timer firing into
dead widgets.

This is the local reproducer for issue #1048 "failure mode 4" -- the
nondeterministic mid-session teardown segfault. The mechanism: a deferred
Qt callback (a ``QTimer.singleShot`` or a polling ``QTimer``) outlives the
widget it references; when it fires, it lands on a destroyed C++ object.
Python-visible symptom: ``RuntimeError: Internal C++ object ... already
deleted`` printed to stderr from the event loop. Native symptom, when the
freed memory has been reused: a segfault in an unrelated place.

Why a stress loop: single build/teardown runs on a fast dev machine almost
never land a timer tick inside the teardown window, which is exactly why
this class of bug was repeatedly caught by CI (slow shared runners, 11
jobs sampling the race per push) and not locally. Cycling build → close →
pump-past-every-timer-deadline N times, then failing on ANY "already
deleted" in captured stderr, gives the race enough chances to lose
locally.

The stderr rule is the important part: an "already deleted" RuntimeError
from a timer callback is never benign noise -- it is the visible tip of a
use-after-free that shows up natively elsewhere. Earlier in this repo's
history one was dismissed as a cosmetic at-exit artifact; CI then
demonstrated the same leak class as real segfaults.
"""

import gc

import pytest

pytest.importorskip("PySide6")

# The longest deferred-callback deadline in the GUI is the log widget's
# 1500 ms welcome message; pump comfortably past it so every timer that
# is going to fire has fired while we are still watching stderr.
_PUMP_MS = 2000
_CYCLES = 3


def _pump(app, ms):
    """Drive the event loop for ``ms`` wall-clock milliseconds."""
    from PySide6.QtCore import QElapsedTimer, QEventLoop

    elapsed = QElapsedTimer()
    elapsed.start()
    while elapsed.elapsed() < ms:
        app.processEvents(QEventLoop.AllEvents, 50)
    # One drain for anything queued at the boundary.
    app.processEvents()


def test_repeated_build_teardown_leaves_no_dead_timer_callbacks(capfd):
    """Build and tear down MetalGUI several times in one process, pumping
    the event loop past every timer deadline after each teardown, and
    fail on any sign of a callback landing on a destroyed object."""
    from PySide6.QtWidgets import QApplication

    from qiskit_metal import designs
    from qiskit_metal._gui.main_window import MetalGUI
    from qiskit_metal.qlibrary.qubits.transmon_pocket import TransmonPocket

    for cycle in range(_CYCLES):
        design = designs.DesignPlanar()
        gui = MetalGUI(design)
        app = QApplication.instance()
        try:
            TransmonPocket(design, "Q1")
            gui.rebuild()
            _pump(app, 300)
        finally:
            gui.main_window.force_close = True
            gui.main_window.close()

        del gui, design
        gc.collect()

        # The dangerous window: widgets are gone, but any leaked timer is
        # still armed. Pump long enough for all of them to come due.
        _pump(app, _PUMP_MS)

        captured = capfd.readouterr()
        combined = captured.out + captured.err
        assert "already deleted" not in combined, (
            f"cycle {cycle}: a deferred Qt callback fired on a destroyed "
            "object -- a use-after-free of the issue #1048 failure-mode-4 "
            "class. Find the unparented QTimer/singleShot and parent it "
            "to the widget it touches (see single_shot() in "
            "_gui/utility/_toolbox_qt.py).\n"
            f"--- captured output ---\n{combined[-3000:]}"
        )
