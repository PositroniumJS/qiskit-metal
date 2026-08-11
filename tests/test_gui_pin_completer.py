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

"""Browsable completion for route endpoints.

A route's endpoints are entered as ``pin_inputs -> start_pin ->
{component, pin}``. Both were plain text fields, so they had to be typed from
memory and a typo only surfaced when the component failed to build.

The interesting part is that the two fields are *coupled*: ``pin`` is only
meaningful for the component named by its sibling ``component`` field, so the
pin list has to narrow to that component rather than offering every pin in the
design. These tests pin that relationship, and that ordinary fields are left
with their normal editor.
"""

import pytest

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget  # noqa: E402

from qiskit_metal.designs.design_planar import DesignPlanar  # noqa: E402
from qiskit_metal.qlibrary.qubits.transmon_pocket import TransmonPocket  # noqa: E402
from qiskit_metal._gui.widgets.create_component_window.model_view.tree_delegate_param_entry import (  # noqa: E402
    ParamDelegate,
)
from qiskit_metal._gui.widgets.create_component_window.model_view.tree_model_param_entry import (  # noqa: E402
    TreeModelParamEntry,
)


class FakeLeaf:
    """A leaf node: a named value with a parent branch."""

    def __init__(self, name, value, parent=None):
        self.name = name
        self.value = value
        self.parent = parent


class FakeBranch:
    """A branch node holding ``(name, node)`` children, as the real one does."""

    def __init__(self, children):
        self.children = [(child.name, child) for child in children]


class FakeIndex:
    """Stands in for a QModelIndex pointing at one node."""

    def __init__(self, node, column=TreeModelParamEntry.VALUE):
        self._node = node
        self._column = column

    def model(self):
        """The index doubles as its own model, which is all the delegate needs."""
        return self

    def nodeFromIndex(self, _index):
        """Mirror TreeModelParamEntry.nodeFromIndex."""
        return self._node

    def column(self):
        """Mirror QModelIndex.column."""
        return self._column


@pytest.fixture(name="qapp", scope="module")
def qapp_fixture():
    """A QApplication; platform passed as an argument, not an env var."""
    return QApplication.instance() or QApplication(
        ["qiskit-metal-tests", "-platform", "offscreen"]
    )


@pytest.fixture(name="design")
def design_fixture():
    """Two transmons: Q1 with pads a and b, Q2 with only a."""
    design = DesignPlanar()
    TransmonPocket(
        design,
        "Q1",
        options=dict(
            pos_x="-1mm", pos_y="0mm", connection_pads=dict(a=dict(), b=dict())
        ),
    )
    TransmonPocket(
        design,
        "Q2",
        options=dict(pos_x="1mm", pos_y="0mm", connection_pads=dict(a=dict())),
    )
    return design


@pytest.fixture(name="delegate")
def delegate_fixture(design, qapp):  # pylint: disable=unused-argument
    """A delegate whose parent window exposes the design."""

    class Window(QWidget):
        """Stand-in for ParameterEntryWindow."""

        _design = design

    window = Window()
    yield ParamDelegate(window)
    window.deleteLater()


def endpoint_nodes(component_value=""):
    """Build a ``start_pin`` branch with coupled component/pin leaves."""
    component = FakeLeaf("component", component_value)
    pin = FakeLeaf("pin", "")
    branch = FakeBranch([component, pin])
    component.parent = branch
    pin.parent = branch
    return component, pin


class TestComponentField:
    """The component field offers the design's components."""

    def test_lists_every_component(self, delegate, design):
        """Whatever is in the design is selectable."""
        component, _ = endpoint_nodes()

        assert sorted(delegate._completions_for(FakeIndex(component))) == sorted(
            design.components.keys()
        )


class TestPinFieldIsScopedToItsComponent:
    """The coupling that makes this more than a flat dropdown."""

    def test_offers_only_that_component_pins(self, delegate):
        """Q1 has two pads."""
        component, pin = endpoint_nodes("Q1")

        assert sorted(delegate._completions_for(FakeIndex(pin))) == ["a", "b"]

    def test_narrows_when_the_component_changes(self, delegate):
        """Q2 has one, so its pin list must be shorter."""
        component, pin = endpoint_nodes("Q2")

        assert sorted(delegate._completions_for(FakeIndex(pin))) == ["a"]

    def test_falls_back_to_all_pins_when_no_component_chosen(self, delegate):
        """Better to offer the union than an empty popup."""
        _, pin = endpoint_nodes("")

        assert sorted(delegate._completions_for(FakeIndex(pin))) == ["a", "b"]

    def test_unknown_component_falls_back(self, delegate):
        """A typo or deleted component must not produce an empty list."""
        _, pin = endpoint_nodes("does-not-exist")

        assert sorted(delegate._completions_for(FakeIndex(pin))) == ["a", "b"]


class TestOrdinaryFields:
    """Everything else keeps the plain editor."""

    def test_no_completions_for_a_normal_option(self, delegate):
        """``pos_x`` is a free value, not a reference."""
        assert delegate._completions_for(FakeIndex(FakeLeaf("pos_x", "0mm"))) == []

    def test_no_design_means_no_completions(self, qapp):  # pylint: disable=unused-argument
        """The dialog can exist before a design is bound."""
        window = QWidget()
        try:
            delegate = ParamDelegate(window)
            component, _ = endpoint_nodes()
            assert delegate._completions_for(FakeIndex(component)) == []
        finally:
            window.deleteLater()


class TestEditorConstruction:
    """The popup has to be browsable, not just filter-as-you-type."""

    def test_editor_has_a_completer(self, delegate, qapp):  # pylint: disable=unused-argument
        """Without one, the field is still free text."""
        editor = delegate._make_completing_editor(None, ["Q1", "Q2"])

        assert isinstance(editor, QLineEdit)
        assert editor.completer() is not None

    def test_popup_shows_everything_before_typing(self, delegate, qapp):  # pylint: disable=unused-argument
        """Arrow-key browsing is the point; filtered mode hides the list."""
        from PySide6.QtWidgets import QCompleter

        editor = delegate._make_completing_editor(None, ["Q1", "Q2"])

        assert editor.completer().completionMode() == (
            QCompleter.UnfilteredPopupCompletion
        )

    def test_completions_are_sorted(self, delegate, qapp):  # pylint: disable=unused-argument
        """A stable order makes the list scannable."""
        editor = delegate._make_completing_editor(None, ["Q2", "Q1"])
        model = editor.completer().model()

        assert [model.data(model.index(i, 0)) for i in range(model.rowCount())] == [
            "Q1",
            "Q2",
        ]
