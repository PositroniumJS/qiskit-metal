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

"""Tree model over ``design.chips`` — the chip stack.

Components, variables and pins each had a dock; the chip stack did not, even
though it holds the die size every design depends on and the layer bounds the
renderers read. Changing it meant dropping to a notebook.

``design.chips`` is a nested ``Dict`` of exactly the shape
``QTreeModel_Base`` already handles, so this is the same editor the component
options pane uses, pointed at a different dictionary::

    chips
      main
        material, layer_start, layer_end
        size
          center_x/y/z, size_x/y/z, sample_holder_top/bottom

Edits go through ``QTreeModel_Base.setData``, which triggers a full
``design.rebuild()`` for ``optionstype == "chip"`` — chip geometry is shared,
so rebuilding a single component would leave the rest stale.
"""

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QTreeView, QWidget

from qiskit_metal._gui.widgets.bases.dict_tree_base import QTreeModel_Base

if TYPE_CHECKING:
    from qiskit_metal._gui.main_window import MetalGUI


class QTreeModel_Chips(QTreeModel_Base):
    """Editable tree over the design's chip stack.

    Args:
        QTreeModel_Base (QAbstractItemModel): Base class for nested dicts.
    """

    def __init__(self, parent: QWidget, gui: "MetalGUI", view: QTreeView):
        """Editable tree for ``design.chips``.

        Args:
            parent (QWidget): The parent widget.
            gui (MetalGUI): The main user interface.
            view (QTreeView): View corresponding to a tree structure.
        """
        super().__init__(parent=parent, gui=gui, view=view, child="chip")

    @property
    def data_dict(self) -> dict:
        """Return a reference to the design's chip dictionary.

        A live reference, not a copy: ``setData`` writes through it.

        Returns an empty dict when no design is set yet. The dock is built
        during ``MetalGUI.__init__``, before ``set_design`` runs, and the
        base class loads immediately on construction; the inherited refresh
        timer repopulates the tree once a design exists.
        """
        design = self.design
        if design is None:
            return {}
        return design.chips

    def _after_reset(self):
        """Re-expand and autofit after every reset, not just the first load.

        The chip stack is a shallow tree (one or two chips, a handful of
        properties each) meant to come up expanded -- but a *every* full
        reset (``beginResetModel``/``endResetModel``) collapses all rows,
        with no general way to preserve expand state across an arbitrary
        tree shape. The base class's polling timer causes exactly one such
        reset ~500ms after construction (its ``_row_count`` sentinel of -1
        always counts as "changed" on the first tick), which silently
        undid a one-time ``expandAll()`` call in ``main_window.py`` shortly
        after the GUI appeared to expand correctly.
        """
        if self._view:
            self._view.expandAll()
            self._view.autoresize_columns()
