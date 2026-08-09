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
"""Main module that handles the entier plot window which is docked inside the
main window.

This can be undocked and can have its own toolbar. this is largley why I
decided to use a QMainWindow, so that we can have inner docking and
toolbars available.
"""

from typing import TYPE_CHECKING

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
)

from qiskit_metal import config

if not config.is_building_docs():
    # Only import PlotCanvas if the docs are NOT being built
    from qiskit_metal.renderers.renderer_mpl.mpl_canvas import PlotCanvas

from qiskit_metal._gui.plot_window_ui import Ui_MainWindowPlot

if TYPE_CHECKING:
    # https://stackoverflow.com/questions/39740632/python-type-hinting-without-cyclic-imports
    from ...main_window import MetalGUI, QMainWindowExtension


# Bindings come from ``renderers.renderer_mpl.mpl_interaction.PanAndZoom``:
# left drag pans, right drag rubber-band zooms, the wheel zooms about the
# cursor, and the autoscale QAction is bound to "A".
NAVIGATION_HELP_HTML = """
<h3>Navigating the plot</h3>
<table cellpadding="4">
  <tr><td><b>Pan</b></td>
      <td>Drag with the <b>left</b> mouse button.</td></tr>
  <tr><td><b>Zoom</b></td>
      <td>Scroll the mouse wheel. Zoom centres on the pointer, so put it
          over the region you care about.</td></tr>
  <tr><td><b>Zoom to region</b></td>
      <td>Drag with the <b>right</b> mouse button to rubber-band a
          rectangle. Drags shorter than a few pixels are ignored.</td></tr>
  <tr><td><b>Fit to design</b></td>
      <td>Press <b>A</b>, or use the autoscale button on the toolbar.</td></tr>
</table>
<p>Editing a component's options replots without moving the camera, so your
current zoom and pan are preserved.</p>
"""


class QMainWindowPlot(QMainWindow):
    """This is just a handler (container) for the UI; it a child object of the
    main gui.

    Extends the `QMainWindow` class

    PySide2 Signal / Slots Extensions:
        The UI can call up to this class to execeute button clicks for instance
        Extensiosn in qt designer on signals/slots are linked to this class

    Core canvas plot widget:
        canvas: The core plot object. Can be mpl or any other renderer.
    """

    def __init__(self, gui: "MetalGUI", parent_window: "QMainWindowExtension"):
        """
        Args:
            gui (MetalGUI): The GUI
            parent_window (QMainWindowExtension): Parent window
        """
        # Q Main WIndow
        super().__init__(parent_window)

        # Parent GUI related
        self.gui = gui
        self.logger = gui.logger
        self.statusbar_label = gui.statusbar_label

        # UI
        self.ui = Ui_MainWindowPlot()
        self.ui.setupUi(self)

        self.statusBar().hide()

        # Add MPL plot widget to window
        # Core object -- the center of this entire widget
        self.canvas = PlotCanvas(
            self.design, self, logger=self.logger, statusbar_label=self.statusbar_label
        )

        self.ui.centralwidget.layout().addWidget(self.canvas)

        self._add_label_actions()

    def _add_label_actions(self):
        """Add the component-labelling actions to the plot toolbar.

        Added here rather than in the .ui because ``plot_window_ui.py`` is
        pyside6-uic output and is regenerated from the .ui on demand.
        """
        toolbar = self.ui.toolBar

        toolbar.addSeparator()

        self.action_label_all = QAction("Label all", self)
        self.action_label_all.setShortcut("L")
        self.action_label_all.setShortcutContext(Qt.WindowShortcut)
        self.action_label_all.setStatusTip(
            "Label every component and its pins (L). Cleared by the next replot."
        )
        self.action_label_all.setToolTip(self.action_label_all.statusTip())
        self.action_label_all.triggered.connect(self.label_all_components)
        toolbar.addAction(self.action_label_all)

        self.action_label_components = QAction("Label components", self)
        self.action_label_components.setShortcut("Shift+L")
        self.action_label_components.setShortcutContext(Qt.WindowShortcut)
        self.action_label_components.setStatusTip(
            "Label components without pins (Shift+L). Cleared by the next replot."
        )
        self.action_label_components.setToolTip(
            self.action_label_components.statusTip()
        )
        self.action_label_components.triggered.connect(
            self.label_components_without_pins
        )
        toolbar.addAction(self.action_label_components)

        self.action_fit_chip = QAction("Fit chip", self)
        self.action_fit_chip.setShortcut("Shift+A")
        self.action_fit_chip.setShortcutContext(Qt.WindowShortcut)
        self.action_fit_chip.setStatusTip(
            "Frame the whole chip including the die outline (Shift+A). "
            "Plain autoscale (A) frames the components only."
        )
        self.action_fit_chip.setToolTip(self.action_fit_chip.statusTip())
        self.action_fit_chip.triggered.connect(self.auto_scale_chip)
        toolbar.addAction(self.action_fit_chip)

        self.action_clear_labels = QAction("Clear labels", self)
        self.action_clear_labels.setShortcut("Shift+C")
        self.action_clear_labels.setShortcutContext(Qt.WindowShortcut)
        self.action_clear_labels.setStatusTip("Remove all component labels (Shift+C).")
        self.action_clear_labels.setToolTip(self.action_clear_labels.statusTip())
        self.action_clear_labels.triggered.connect(self.clear_labels)
        toolbar.addAction(self.action_clear_labels)

    def label_all_components(self):
        """Label every component, including its pins."""
        self.gui.highlight_all_components(show_pins=True)

    def label_components_without_pins(self):
        """Label every component, omitting pins."""
        self.gui.highlight_all_components(show_pins=False)

    def clear_labels(self):
        """Remove component labels from the canvas."""
        self.gui.clear_highlight()

    def keyPressEvent(self, event):
        """Delegate to the canvas's own nudge handling.

        The nudge logic used to live here, but this container never
        actually receives the key events in practice -- the canvas is the
        widget that holds keyboard focus after a click-select, and
        ``FigureCanvas`` (its base class) does not propagate unhandled
        keys up to the parent. Moved to
        ``PlotCanvas.keyPressEvent``; kept here as a defensive delegate in
        case this window itself ever ends up with focus by some other
        path.

        Args:
            event (QKeyEvent): The key event.
        """
        self.canvas.keyPressEvent(event)
        event.accept()

    def set_design(self, design):
        """Set the design.

        Args:
            design (QDesign): Design to set the canvas to
        """
        self.canvas.set_design(design)

    @property
    def design(self):
        """Returns the design."""
        return self.gui.design

    def replot(self):
        """Tells the canvas to replot."""
        # self.logger.debug("Force replot")
        self.canvas.plot()

    def auto_scale(self, include_chip: bool = False):
        """Tells the canvas to perform an automatic scale.

        Args:
            include_chip (bool): Frame the whole chip rather than just the
                components. Defaults to False.
        """
        self.logger.debug("Autoscale (include_chip=%s)", include_chip)
        self.canvas.auto_scale(include_chip=include_chip)

    def auto_scale_chip(self):
        """Frame the whole chip, including the die outline."""
        self.auto_scale(include_chip=True)

    def _navigation_help(self, title: str):
        """Show the shared navigation cheat-sheet.

        Args:
            title (str): Dialog title, so the Pan and Zoom toolbar buttons
                can each open it under their own name.
        """
        QMessageBox.about(self, title, NAVIGATION_HELP_HTML)

    def pan(self):
        """Displays a message about how to navigate the plot."""
        self._navigation_help("Pan")

    def zoom(self):
        """Displays a message about how to navigate the plot."""
        self._navigation_help("Zoom")

    def set_position_track(self, yesno: bool):
        """Set the position tracker.

        Args:
            yesno (bool): Whether or not to display instructions
        """
        if yesno:
            self.logger.info("Click a point in the plot window to see its coordinate.")
        self.canvas.panzoom.options.report_point_position = yesno

    def set_show_pins(self, yesno: bool):
        """Displays on the logger whether or not pins are showing.

        Args:
            yesno (bool): Whether or not to show pins
        """
        self.logger.info(f"Showing pins: {yesno}")
