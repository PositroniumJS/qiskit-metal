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

"""``QTreeModel_Base``'s polling ``QTimer`` must not touch a destroyed view.

The model and its view can be torn down independently -- closing a dock or
dialog destroys the view, but the model's own ``QTimer`` (parented to the
model, not the view) keeps firing on its 500ms cadence regardless and calls
back into ``self._view`` on every tick.

This was caught via CI, not locally: a real on-screen/native run of the
full suite showed segfaults and self-heal-test failures in
``test_gui_init.py`` (issue #1048 failure mode 4, the "mid-session GC
teardown segfault") that traced back to
``tests/test_gui_nudge.py::TestRealClickAndKeyDelivery`` leaving one of
these timers alive past a dock's destruction. It had looked like a benign,
exit-code-0 artifact under a plain headless ``pytest`` run (see the
"Still open" note in ``docs/architecture/gui_crash_defenses.md`` predating
this fix) -- CI's real display and larger, longer-lived Qt object graph is
what actually surfaced the use-after-free.
"""

import pytest

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
import shiboken6  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from qiskit_metal import designs  # noqa: E402
from qiskit_metal._gui.tree_view_base import QTreeView_Base  # noqa: E402
from qiskit_metal._gui.widgets.edit_chip.tree_model_chips import (  # noqa: E402
    QTreeModel_Chips,
)


class _FakeLogger:
    def debug(self, *_a, **_kw):
        pass

    def info(self, *_a, **_kw):
        pass


class _FakeGui:
    def __init__(self, design):
        self.logger = _FakeLogger()
        self.design = design


@pytest.fixture(name="qapp")
def qapp_fixture():
    app = QApplication.instance() or QApplication([])
    yield app


def test_auto_refresh_survives_a_destroyed_view(qapp):
    """Destroy the view out from under the model, then let the polling
    timer tick -- it must neither raise nor touch the dead view again."""
    design = designs.DesignPlanar()
    gui = _FakeGui(design)
    view = QTreeView_Base(None)
    model = QTreeModel_Chips(parent=None, gui=gui, view=view)
    view.setModel(model)

    assert model.timer.isActive()

    # Force a rowcount change so auto_refresh() would normally do real work
    # (reset the model, then touch self._view) on the next tick.
    design.chips["extra"] = {"layer_start": "0", "layer_end": "1"}
    model._row_count = -1  # pylint: disable=protected-access

    # Simulate the dock/dialog closing: the view's C++ object goes away,
    # but the model (and its timer) were never told.
    shiboken6.delete(view)
    assert not shiboken6.isValid(view)

    # This is the polling timer's callback, invoked directly rather than
    # waiting out the real 500ms -- must not raise.
    model.auto_refresh()

    # No point polling for a view that no longer exists.
    assert not model.timer.isActive()


def test_auto_refresh_keeps_working_with_a_live_view(qapp):
    """Sanity check the guard doesn't false-positive on a normal, live view
    and stop refreshing something that's still on screen."""
    design = designs.DesignPlanar()
    gui = _FakeGui(design)
    view = QTreeView_Base(None)
    model = QTreeModel_Chips(parent=None, gui=gui, view=view)
    view.setModel(model)

    design.chips["extra"] = {"layer_start": "0", "layer_end": "1"}
    model._row_count = -1  # pylint: disable=protected-access

    model.auto_refresh()

    assert model.timer.isActive()
