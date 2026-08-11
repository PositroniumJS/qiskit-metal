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

"""Editing the chip stack from the GUI.

Components, variables and pins each had a dock; ``design.chips`` did not,
despite holding the die size every design depends on and the layer bounds the
renderers read. Changing it meant dropping to a notebook.

``design.chips`` is a nested ``Dict`` of the same shape the component-options
tree already edits, so ``QTreeModel_Chips`` reuses ``QTreeModel_Base`` rather
than adding a second editor. Two things are specific to chips and are what
these tests cover:

- an edit must trigger a **full** ``design.rebuild()``, not one component's,
  because chip geometry is shared by every component and the die outline;
- the model is constructed during ``MetalGUI.__init__``, *before* the design
  is set, so ``data_dict`` has to tolerate ``design is None``.
"""

import matplotlib
import pytest

matplotlib.use("Agg")

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
from PySide6.QtCore import QModelIndex, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QTreeView, QWidget  # noqa: E402

from qiskit_metal.designs.design_planar import DesignPlanar  # noqa: E402
from qiskit_metal._gui.widgets.edit_chip import QTreeModel_Chips  # noqa: E402


class FakeLogger:
    """Absorbs the model's log calls."""

    def info(self, *_, **__):
        """Ignore."""

    def warning(self, *_, **__):
        """Ignore."""

    def error(self, *_, **__):
        """Ignore."""

    def debug(self, *_, **__):
        """Ignore."""


class FakeGui:
    """The slice of MetalGUI the tree model reads."""

    def __init__(self, design):
        self.design = design
        self.logger = FakeLogger()
        self.refreshed = 0

    def refresh(self):
        """Count refreshes so the rebuild path can be asserted."""
        self.refreshed += 1


@pytest.fixture(name="qapp", scope="module")
def qapp_fixture():
    """A QApplication; platform passed as an argument, not an env var."""
    return QApplication.instance() or QApplication(
        ["qiskit-metal-tests", "-platform", "offscreen"]
    )


@pytest.fixture(name="design")
def design_fixture():
    """A default planar design: one 9x6mm chip named ``main``."""
    return DesignPlanar()


@pytest.fixture(name="model")
def model_fixture(design, qapp):  # pylint: disable=unused-argument
    """A chip tree model over that design."""
    parent = QWidget()
    view = QTreeView(parent)
    model = QTreeModel_Chips(parent, gui=FakeGui(design), view=view)
    model.load()
    yield model
    parent.deleteLater()


def find_value_index(model, label, parent=QModelIndex()):
    """Return the editable (column 1) index of the leaf with ``label``."""
    for row in range(model.rowCount(parent)):
        name_index = model.index(row, 0, parent)
        node = model.nodeFromIndex(name_index)
        if getattr(node, "label", None) == label:
            return model.index(row, 1, parent)
        found = find_value_index(model, label, name_index)
        if found is not None:
            return found
    return None


class TestModelReflectsTheChipStack:
    """The tree shows what is actually in ``design.chips``."""

    def test_top_level_is_the_chip_names(self, model, design):
        """One row per chip."""
        assert [name for name, _ in model.root.children] == list(design.chips.keys())

    def test_nested_size_is_reachable(self, model):
        """``size_x`` lives two levels down, under main -> size."""
        assert find_value_index(model, "size_x") is not None

    def test_shows_the_current_value(self, model, design):
        """Displayed value tracks the design, not a snapshot."""
        index = find_value_index(model, "size_x")
        assert model.data(index, Qt.DisplayRole) == design.chips.main.size.size_x


class TestEditing:
    """Edits write through and rebuild the design."""

    def test_edit_updates_the_design(self, model, design):
        """The model holds a live reference, not a copy."""
        index = find_value_index(model, "size_x")

        assert model.setData(index, "12mm", Qt.EditRole) is True
        assert design.chips.main.size.size_x == "12mm"

    def test_edit_triggers_a_full_rebuild(self, model, design, monkeypatch):
        """Chip geometry is shared, so one component's rebuild is not enough."""
        rebuilds = []
        monkeypatch.setattr(design, "rebuild", lambda *a, **k: rebuilds.append(1))

        model.setData(find_value_index(model, "size_x"), "12mm", Qt.EditRole)

        assert len(rebuilds) == 1

    def test_edit_refreshes_the_gui(self, model, design, monkeypatch):
        """The canvas has to redraw or the new die outline is invisible."""
        monkeypatch.setattr(design, "rebuild", lambda *a, **k: None)

        model.setData(find_value_index(model, "size_x"), "12mm", Qt.EditRole)

        assert model.gui.refreshed == 1

    def test_setting_the_same_value_is_a_no_op(self, model, design, monkeypatch):
        """Re-entering the current value must not rebuild the whole design."""
        rebuilds = []
        monkeypatch.setattr(design, "rebuild", lambda *a, **k: rebuilds.append(1))
        current = design.chips.main.size.size_x

        assert (
            model.setData(find_value_index(model, "size_x"), current, Qt.EditRole)
            is False
        )
        assert not rebuilds


class TestNoDesignYet:
    """The dock is built before ``set_design`` runs."""

    def test_data_dict_is_empty_without_a_design(self, qapp):  # pylint: disable=unused-argument
        """Must not raise AttributeError on ``None.chips``."""
        parent = QWidget()
        view = QTreeView(parent)
        try:
            model = QTreeModel_Chips(parent, gui=FakeGui(None), view=view)
            assert model.data_dict == {}
        finally:
            parent.deleteLater()

    def test_populates_once_a_design_arrives(self, design, qapp):  # pylint: disable=unused-argument
        """The refresh path fills the tree in later."""
        parent = QWidget()
        view = QTreeView(parent)
        try:
            gui = FakeGui(None)
            model = QTreeModel_Chips(parent, gui=gui, view=view)
            assert not model.root.children

            gui.design = design
            model.load()
            assert [name for name, _ in model.root.children] == list(
                design.chips.keys()
            )
        finally:
            parent.deleteLater()
