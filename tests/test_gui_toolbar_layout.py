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

"""Declarative toolbar composition.

Toolbar contents used to live in ``main_window_ui.ui`` and be patched
afterwards in ``_ui_adjustments``. ``toolbar_layout`` replaces that with a
data structure, so ordering and priority are a one-line edit.

The risk in moving composition into code is silently losing an action: drop a
name from the spec and its button just disappears, with nothing to notice.
``check_no_actions_lost`` is the guard against that, and most of these tests
exercise it rather than the happy path.

Pure-data tests here; the actions are resolved off ``gui.ui`` with lightweight
fakes rather than by constructing a MetalGUI, so no display is needed.
"""

import pytest

from qiskit_metal._gui import toolbar_layout as tl


class FakeAction:
    """Enough QAction surface for the layout code."""

    def __init__(self, name, separator=False):
        self._name = name
        self._separator = separator

    def isSeparator(self):
        """Mirror QAction.isSeparator."""
        return self._separator

    def objectName(self):
        """Mirror QAction.objectName."""
        return self._name


class FakeToolbar:
    """Records what the layout adds to it."""

    def __init__(self, actions=()):
        self._actions = list(actions)
        self.cleared = False
        self.icon_size = None
        self.button_style = None

    # -- inspection used by the layout ---------------------------------
    def actions(self):
        """Mirror QToolBar.actions."""
        return self._actions

    # -- mutation performed by the layout ------------------------------
    def clear(self):
        """Mirror QToolBar.clear."""
        self.cleared = True
        self._actions = []

    def addAction(self, action):
        """Mirror QToolBar.addAction."""
        self._actions.append(action)

    def addSeparator(self):
        """Mirror QToolBar.addSeparator."""
        self._actions.append(FakeAction("", separator=True))

    def setToolButtonStyle(self, style):
        """Mirror QToolBar.setToolButtonStyle."""
        self.button_style = style

    def setIconSize(self, size):
        """Mirror QToolBar.setIconSize."""
        self.icon_size = size

    def setContentsMargins(self, *_):
        """Mirror QWidget.setContentsMargins."""

    def layout(self):
        """No layout object on the fake."""
        return


class FakeUI:
    """Attribute bag standing in for the generated ``Ui_MainWindow``."""


class FakeGUI:
    """Minimal object exposing ``.ui``, which is all the layout touches."""

    def __init__(self):
        self.ui = FakeUI()


@pytest.fixture(name="gui")
def gui_fixture():
    """A fake GUI whose toolbars and actions match the real spec."""
    gui = FakeGUI()
    for toolbar_name, names in tl.TOOLBAR_LAYOUT.items():
        setattr(gui.ui, toolbar_name, FakeToolbar())
        for name in names:
            if name is not tl.SEP:
                setattr(gui.ui, name, FakeAction(name))
    for name in tl.DEMOTED_ACTIONS:
        setattr(gui.ui, name, FakeAction(name))
    return gui


class TestSpecIntegrity:
    """The spec itself has to be coherent before it is applied."""

    def test_no_action_placed_twice(self):
        """A duplicate would render the same button on two toolbars."""
        names = list(tl._iter_spec_names())
        assert len(names) == len(set(names))

    def test_placed_and_demoted_are_disjoint(self):
        """An action cannot be both on a toolbar and deliberately off it."""
        assert not set(tl._iter_spec_names()) & set(tl.DEMOTED_ACTIONS)

    def test_every_demotion_states_a_reason(self):
        """The reason distinguishes a decision from an accident."""
        for name, reason in tl.DEMOTED_ACTIONS.items():
            assert reason.strip(), f"{name} demoted with no reason"


class TestApplyLayout:
    """Applying the spec puts the right actions in the right order."""

    def test_actions_match_spec_order(self, gui):
        """Order is the whole point -- most-used first."""
        tl.apply_toolbar_layout(gui)

        for toolbar_name, names in tl.TOOLBAR_LAYOUT.items():
            toolbar = getattr(gui.ui, toolbar_name)
            got = [a.objectName() for a in toolbar.actions() if not a.isSeparator()]
            assert got == [n for n in names if n is not tl.SEP]

    def test_rebuild_is_first(self, gui):
        """The most-used control leads the primary toolbar."""
        tl.apply_toolbar_layout(gui)
        first = gui.ui.toolBarDesign.actions()[0]
        assert first.objectName() == "actionRebuild"

    def test_toolbars_share_one_icon_size(self, gui):
        """Mismatched sizes made the two top bars different heights."""
        tl.apply_toolbar_layout(gui)
        sizes = {getattr(gui.ui, name).icon_size.width() for name in tl.TOOLBAR_LAYOUT}
        assert sizes == {tl.TOOLBAR_ICON_PX}

    def test_applying_twice_is_idempotent(self, gui):
        """Re-running must not double the buttons."""
        tl.apply_toolbar_layout(gui)
        first = [a.objectName() for a in gui.ui.toolBarDesign.actions()]

        tl.apply_toolbar_layout(gui)
        assert [a.objectName() for a in gui.ui.toolBarDesign.actions()] == first

    def test_unknown_action_name_raises(self, gui, monkeypatch):
        """A typo must fail loudly, not silently omit a button."""
        monkeypatch.setitem(tl.TOOLBAR_LAYOUT, "toolBarDesign", ["actionDoesNotExist"])
        with pytest.raises(RuntimeError, match="unknown action"):
            tl.apply_toolbar_layout(gui)


class TestNoActionsLost:
    """The guard that makes code-driven composition safe."""

    def test_unaccounted_action_raises(self, gui):
        """An action on a toolbar but absent from spec and demotions."""
        gui.ui.toolBarDesign = FakeToolbar([FakeAction("actionMystery")])

        with pytest.raises(RuntimeError, match="actionMystery"):
            tl.check_no_actions_lost(gui, tl._collect_existing_action_names(gui))

    def test_demoted_action_is_allowed(self, gui):
        """Deliberate removal is fine -- that is what DEMOTED_ACTIONS records."""
        demoted = next(iter(tl.DEMOTED_ACTIONS))
        gui.ui.toolBarDesign = FakeToolbar([FakeAction(demoted)])

        tl.check_no_actions_lost(gui, tl._collect_existing_action_names(gui))

    def test_placed_action_is_allowed(self, gui):
        """An action the spec places is obviously accounted for."""
        gui.ui.toolBarDesign = FakeToolbar([FakeAction("actionRebuild")])

        tl.check_no_actions_lost(gui, tl._collect_existing_action_names(gui))

    def test_error_names_the_missing_action(self, gui):
        """The message has to say which action, or it is not actionable."""
        gui.ui.toolBarDesign = FakeToolbar([FakeAction("actionSomethingSpecific")])

        with pytest.raises(RuntimeError) as excinfo:
            tl.check_no_actions_lost(gui, tl._collect_existing_action_names(gui))

        assert "actionSomethingSpecific" in str(excinfo.value)
        assert "DEMOTED_ACTIONS" in str(excinfo.value)
