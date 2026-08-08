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

"""Show and hide layers, like a GDS editor's layer palette.

``QMplRenderer`` already supported hiding: it keeps a ``hidden_layers`` set
and ``get_mask`` filters rows whose layer is in it. There was simply no way to
reach that from the GUI, and no way to see which layers a design even
contains -- you had to know, and set it from a notebook.

Layers are read from the qgeometry tables rather than from a declared list,
because that is where they actually come from: a component writes whatever
layer number its options say, and nothing registers it up front.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from qiskit_metal.designs.design_base import QDesign


def design_layers(design: "QDesign") -> list:
    """Return every layer number present in the design's geometry.

    Args:
        design (QDesign): The design to inspect.

    Returns:
        list: Sorted layer numbers. Empty when nothing has been built.
    """
    if design is None:
        return []

    layers = set()
    for table_name in design.qgeometry.tables:
        table = design.qgeometry.tables[table_name]
        if len(table) and "layer" in table:
            layers.update(table.layer.unique().tolist())
    return sorted(layers)


class LayerVisibilityWidget(QWidget):
    """Checkbox per layer, wired to the renderer's ``hidden_layers``."""

    def __init__(self, gui: "MetalGUI", parent: QWidget = None):
        """
        Args:
            gui (MetalGUI): The main user interface.
            parent (QWidget): Parent widget.
        """
        super().__init__(parent)
        self.gui = gui
        self._checkboxes = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        outer.addWidget(self._status)

        container = QWidget(self)
        self._layer_layout = QVBoxLayout(container)
        self._layer_layout.setContentsMargins(0, 0, 0, 0)
        self._layer_layout.setSpacing(2)
        self._layer_layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        show_all = QPushButton("Show all", self)
        show_all.setToolTip("Make every layer visible again")
        show_all.clicked.connect(self.show_all_layers)
        outer.addWidget(show_all)

        self.refresh()

    @property
    def renderer(self):
        """The matplotlib renderer that owns ``hidden_layers``, or None."""
        canvas = getattr(self.gui, "canvas", None)
        return getattr(canvas, "metal_renderer", None)

    def refresh(self):
        """Rebuild the checkbox list from the design's current layers.

        Called when the design changes. Layers only exist once geometry has
        been built, so an empty design legitimately shows nothing.
        """
        for checkbox in self._checkboxes.values():
            self._layer_layout.removeWidget(checkbox)
            checkbox.deleteLater()
        self._checkboxes = {}

        layers = design_layers(getattr(self.gui, "design", None))
        if not layers:
            self._status.setText("No layers yet — build a component first.")
            return

        self._status.setText(f"{len(layers)} layer(s) in this design")
        hidden = getattr(self.renderer, "hidden_layers", set())

        for layer in layers:
            checkbox = QCheckBox(f"Layer {layer}", self)
            checkbox.setChecked(layer not in hidden)
            checkbox.setToolTip(f"Show or hide everything drawn on layer {layer}")
            # Bind the layer per-iteration; a bare closure would capture the
            # loop variable and every box would toggle the last layer.
            checkbox.stateChanged.connect(
                lambda state, lyr=layer: self.set_layer_visible(lyr, bool(state))
            )
            self._layer_layout.insertWidget(self._layer_layout.count() - 1, checkbox)
            self._checkboxes[layer] = checkbox

    def set_layer_visible(self, layer, visible: bool):
        """Show or hide one layer and redraw.

        Args:
            layer: Layer number.
            visible (bool): True to show.
        """
        renderer = self.renderer
        if renderer is None:
            return

        if visible:
            renderer.show_layer(layer)
        else:
            renderer.hide_layer(layer)

        canvas = getattr(self.gui, "canvas", None)
        if canvas is not None:
            canvas.plot()

    def show_all_layers(self):
        """Clear every hidden layer and redraw."""
        renderer = self.renderer
        if renderer is not None:
            renderer.hidden_layers.clear()

        for checkbox in self._checkboxes.values():
            checkbox.blockSignals(True)
            checkbox.setChecked(True)
            checkbox.blockSignals(False)

        canvas = getattr(self.gui, "canvas", None)
        if canvas is not None:
            canvas.plot()
