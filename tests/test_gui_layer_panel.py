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

"""Layer visibility panel, and the layer enumeration behind it.

``QMplRenderer`` already kept a ``hidden_layers`` set and ``get_mask``
filtered on it, but nothing in the GUI could reach that and there was no way
to see which layers a design contains.

Layers are read from the qgeometry tables rather than a declared list, because
that is where they come from: a component writes whatever layer its options
say, and nothing registers it up front. So an empty design legitimately has no
layers, which the panel has to handle rather than look broken.
"""

import matplotlib
import pytest

matplotlib.use("Agg")

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
from PySide6.QtWidgets import QApplication  # noqa: E402

from qiskit_metal.designs.design_planar import DesignPlanar  # noqa: E402
from qiskit_metal.qlibrary.qubits.transmon_pocket import TransmonPocket  # noqa: E402
from qiskit_metal._gui.widgets.view_control import (  # noqa: E402
    LayerVisibilityWidget,
    design_layers,
)


class FakeRenderer:
    """The slice of QMplRenderer the panel drives."""

    def __init__(self):
        self.hidden_layers = set()

    def hide_layer(self, name):
        """Mirror QMplRenderer.hide_layer."""
        self.hidden_layers.add(name)

    def show_layer(self, name):
        """Mirror QMplRenderer.show_layer."""
        self.hidden_layers.discard(name)


class FakeCanvas:
    """Counts replots so the panel's redraw can be asserted."""

    def __init__(self):
        self.metal_renderer = FakeRenderer()
        self.plots = 0

    def plot(self):
        """Mirror PlotCanvas.plot."""
        self.plots += 1


class FakeGui:
    """The slice of MetalGUI the panel reads."""

    def __init__(self, design):
        self.design = design
        self.canvas = FakeCanvas()


@pytest.fixture(name="qapp", scope="module")
def qapp_fixture():
    """A QApplication; platform passed as an argument, not an env var."""
    return QApplication.instance() or QApplication(
        ["qiskit-metal-tests", "-platform", "offscreen"]
    )


@pytest.fixture(name="design")
def design_fixture():
    """A design with one built component, so geometry (and a layer) exists."""
    design = DesignPlanar()
    TransmonPocket(design, "Q1", options=dict(pos_x="0mm", pos_y="0mm"))
    return design


@pytest.fixture(name="panel")
def panel_fixture(design, qapp):  # pylint: disable=unused-argument
    """A layer panel over that design."""
    widget = LayerVisibilityWidget(FakeGui(design))
    yield widget
    widget.deleteLater()


class TestDesignLayers:
    """Enumerating layers from the geometry tables."""

    def test_finds_the_layer_in_use(self, design):
        """The default transmon draws on layer 1."""
        assert design_layers(design) == [1]

    def test_empty_design_has_no_layers(self):
        """Nothing built yet means nothing to list -- not an error."""
        assert design_layers(DesignPlanar()) == []

    def test_none_design_is_tolerated(self):
        """The panel exists before a design is bound."""
        assert design_layers(None) == []


class TestPanelContents:
    """The checkbox list mirrors the design."""

    def test_one_checkbox_per_layer(self, panel):
        """What you see is what the design actually contains."""
        assert list(panel._checkboxes.keys()) == [1]

    def test_layers_start_visible(self, panel):
        """Nothing is hidden until asked."""
        assert panel._checkboxes[1].isChecked()

    def test_refresh_picks_up_a_new_layer(self, panel, design):
        """A component on another layer should appear after a refresh."""
        TransmonPocket(design, "Q2", options=dict(pos_x="2mm", pos_y="0mm", layer="5"))
        panel.refresh()

        assert 5 in panel._checkboxes


class TestToggling:
    """Driving the renderer's hidden_layers."""

    def test_hiding_updates_the_renderer(self, panel):
        """The renderer is the thing that actually filters."""
        panel.set_layer_visible(1, False)

        assert panel.renderer.hidden_layers == {1}

    def test_showing_clears_it(self, panel):
        """Round-trips rather than latching hidden."""
        panel.set_layer_visible(1, False)
        panel.set_layer_visible(1, True)

        assert panel.renderer.hidden_layers == set()

    def test_toggling_redraws(self, panel):
        """Filtering without a redraw would look like nothing happened."""
        before = panel.gui.canvas.plots
        panel.set_layer_visible(1, False)

        assert panel.gui.canvas.plots > before

    def test_show_all_clears_everything(self, panel):
        """The escape hatch after hiding several layers."""
        panel.renderer.hidden_layers.update({1, 2, 3})

        panel.show_all_layers()

        assert panel.renderer.hidden_layers == set()

    def test_show_all_rechecks_the_boxes(self, panel):
        """UI state must agree with the renderer afterwards."""
        panel.set_layer_visible(1, False)
        panel.show_all_layers()

        assert panel._checkboxes[1].isChecked()
