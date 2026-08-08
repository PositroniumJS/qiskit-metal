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

"""Delegate for the existing-component options tree (``component_widget``'s
``treeView``).

The create-component window already offers pin/component-name autocomplete
for these same field names (``ParamDelegate`` in
``create_component_window/model_view/tree_delegate_param_entry.py``), but
that delegate is tied to ``TreeModelParamEntry``'s node type (``.name``,
three fixed columns). This tree instead uses ``dict_tree_base``'s
``LeafNode``/``BranchNode`` (``.label``, a plain KEY/VALUE pair), so the
completion logic is reimplemented against that API rather than shared.
"""

from PySide6.QtCore import QModelIndex, QTimer, Qt
from PySide6.QtWidgets import QCompleter, QItemDelegate, QLineEdit, QWidget

#: Column holding the editable value, per dict_tree_base's KEY/NODE split.
_VALUE_COLUMN = 1

#: Leaf labels that name a QComponent in this design.
_COMPONENT_FIELDS = {"component"}

#: Leaf labels that name a pin on the component named by a sibling field.
_PIN_FIELDS = {"pin"}

#: Leaf labels that name a chip in this design.
_CHIP_FIELDS = {"chip"}


class OptionsCompletingDelegate(QItemDelegate):
    """Offers the same component/pin/chip-name autocomplete as the
    create-component window, for editing an *existing* component's options.
    """

    def __init__(self, gui, parent=None):
        """
        Args:
            gui (MetalGUI): The GUI -- used to read the live design for
                completion candidates.
            parent (QWidget): Parent widget.
        """
        super().__init__(parent=parent)
        self._gui = gui

    def createEditor(self, parent: QWidget, option, index: QModelIndex) -> QWidget:
        """See ParamDelegate.createEditor -- same completions-if-any,
        default line edit otherwise."""
        if index.column() == _VALUE_COLUMN:
            completions = self._completions_for(index)
            if completions:
                return self._make_completing_editor(parent, completions)
        return QItemDelegate.createEditor(self, parent, option, index)

    @staticmethod
    def _make_completing_editor(parent: QWidget, completions: list) -> QLineEdit:
        """A line edit whose completion popup is already open, browsable
        with the arrow keys before typing anything. See ParamDelegate's
        twin method for why the explicit complete() call is necessary.
        """
        editor = QLineEdit(parent)
        completer = QCompleter(sorted(completions), editor)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        completer.setFilterMode(Qt.MatchContains)
        editor.setCompleter(completer)
        QTimer.singleShot(0, completer.complete)
        return editor

    def _completions_for(self, index: QModelIndex) -> list:
        """Candidate values for the field at ``index``, if it names one.

        Args:
            index (QModelIndex): The value cell being edited.

        Returns:
            list: Candidate strings, empty when the field is not a reference.
        """
        design = getattr(self._gui, "design", None)
        if design is None:
            return []

        node = index.model().nodeFromIndex(index)
        label = getattr(node, "label", None)

        if label in _COMPONENT_FIELDS:
            return list(design.components.keys())

        if label in _CHIP_FIELDS:
            return list(design.chips.keys())

        if label in _PIN_FIELDS:
            component_name = self._sibling_value(node, _COMPONENT_FIELDS)
            if not component_name or component_name not in design.components:
                pins = set()
                for component in design.components.values():
                    pins.update(component.pins.keys())
                return sorted(pins)
            return list(design.components[component_name].pins.keys())

        return []

    @staticmethod
    def _sibling_value(node, labels: set):
        """Value of the sibling leaf whose label is in ``labels``.

        ``pin`` is only meaningful alongside the ``component`` it belongs
        to, and they sit under the same parent branch.

        Args:
            node: The leaf node being edited.
            labels (set): Sibling labels to look for.

        Returns:
            The sibling's value, or None.
        """
        parent = getattr(node, "parent", None)
        if parent is None:
            return None
        for _, sibling in getattr(parent, "children", []):
            if getattr(sibling, "label", None) in labels:
                return getattr(sibling, "value", None)
        return None
