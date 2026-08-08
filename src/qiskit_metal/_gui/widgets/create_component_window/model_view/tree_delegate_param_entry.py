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
"""
Delegate for Param Entry Window's MVD
"""

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QCompleter,
    QItemDelegate,
    QLineEdit,
    QStyleOptionViewItem,
    QWidget,
)

from qiskit_metal._gui.widgets.create_component_window.model_view.tree_model_param_entry import (
    TreeModelParamEntry,
)

#: Leaf names that name a QComponent in this design.
_COMPONENT_FIELDS = {"component"}

#: Leaf names that name a pin on the component named by a sibling field.
_PIN_FIELDS = {"pin"}


class ParamDelegate(QItemDelegate):
    """
    ParamDelegate for controlling specific UI display
    (such as QComboBoxes) for the Parameter Entry Window
    """

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QWidget:
        """
        Overriding inherited createdEditor class.
        Note that the index contains information about the model being used.
        The editor's parent widget is specified by parent, and the item options by option.

        Args:
            parent (QWidget): Parent widget
            option (QStyleOptionViewItem): Style options for the related view
            index (QModelIndex): Specific index being edited

        Returns:
            Returns the editor to be used for editing the data item with the given index.
        """
        if index.column() == TreeModelParamEntry.TYPE:
            node = index.model().nodeFromIndex(index)
            combo = node.get_type_combobox(parent)  # dicts vs values
            return combo

        if index.column() == TreeModelParamEntry.VALUE:
            completions = self._completions_for(index)
            if completions:
                return self._make_completing_editor(parent, completions)

        return QItemDelegate.createEditor(self, parent, option, index)

    @staticmethod
    def _make_completing_editor(parent: QWidget, completions: list) -> QLineEdit:
        """Return a line edit with a browsable completion popup.

        ``UnfilteredPopupCompletion`` shows the whole list as soon as the
        editor opens, so the field can be browsed with the arrow keys without
        knowing what to type first -- the point of the feature. Filtering
        still happens as you type.

        Args:
            parent (QWidget): Parent widget for the editor.
            completions (list): Candidate strings.

        Returns:
            QLineEdit: The editor.
        """
        editor = QLineEdit(parent)
        completer = QCompleter(sorted(completions), editor)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        completer.setFilterMode(Qt.MatchContains)
        editor.setCompleter(completer)
        return editor

    def _completions_for(self, index: QModelIndex) -> list:
        """Candidate values for the field at ``index``, if it names one.

        Route endpoints are entered as ``pin_inputs -> start_pin ->
        {component, pin}``. Both were free-text, so they had to be typed from
        memory and a typo only surfaced at build time.

        Args:
            index (QModelIndex): The value cell being edited.

        Returns:
            list: Candidate strings, empty when the field is not a reference.
        """
        design = self._design()
        if design is None:
            return []

        node = index.model().nodeFromIndex(index)
        name = getattr(node, "name", None)

        if name in _COMPONENT_FIELDS:
            return list(design.components.keys())

        if name in _PIN_FIELDS:
            component_name = self._sibling_value(node, _COMPONENT_FIELDS)
            if not component_name or component_name not in design.components:
                # No component chosen yet, so no pin list can be narrowed to
                # it. Offer every pin name in the design rather than nothing.
                pins = set()
                for component in design.components.values():
                    pins.update(component.pins.keys())
                return sorted(pins)
            return list(design.components[component_name].pins.keys())

        return []

    @staticmethod
    def _sibling_value(node, names: set):
        """Value of the sibling leaf whose name is in ``names``.

        ``pin`` is only meaningful alongside the ``component`` it belongs to,
        and they sit under the same parent branch.

        Args:
            node: The leaf node being edited.
            names (set): Sibling names to look for.

        Returns:
            str: The sibling's value, or None.
        """
        parent = getattr(node, "parent", None)
        if parent is None:
            return None
        for _, sibling in getattr(parent, "children", []):
            if getattr(sibling, "name", None) in names:
                return getattr(sibling, "value", None)
        return None

    def _design(self):
        """Return the design the dialog is editing, or None.

        The delegate's parent is the ``ParameterEntryWindow``.
        """
        window = self.parent()
        return getattr(window, "_design", None)

    def setEditorData(self, editor: QWidget, index: QModelIndex):
        """
        Overriding inherited setEditorData class
        Args:
            editor (QWidget): Current editor for the data
            index (QModelIndex): Current index being modified

        """
        text = index.model().data(index, Qt.DisplayRole)
        if index.column() == TreeModelParamEntry.TYPE:
            editor.setCurrentText(text)
        else:
            QItemDelegate.setEditorData(self, editor, index)

    def setModelData(
        self, editor: QWidget, model: QAbstractItemModel, index: QModelIndex
    ):
        """
        Overriding inherited setModelData class
        Args:
            editor (QWidget): Current editor for the data
            model (QAbstractItemModel): Current model whose data is being set
            index (QModelIndex): Current index being modified

        """
        if index.column() == TreeModelParamEntry.TYPE:
            model.setData(index, editor.getTypeName())
            # get type
            # get corresponding dict entry
            # update type (OrderedDict, str, etc.)  as necessary
            # get value
        else:
            QItemDelegate.setModelData(self, editor, model, index)
