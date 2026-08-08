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

"""Declarative toolbar layout for :class:`MetalGUI`.

The window's widgets and actions come from ``main_window_ui.ui``, compiled to
``main_window_ui.py`` by ``pyside6-uic``. That file is generated, so it cannot
be hand-edited, and Qt Designer is the only way to change what it says --
which is why toolbar tweaks had to be applied as after-the-fact overrides in
``_ui_adjustments``, and why the two top toolbars drifted to different icon
sizes and the side toolbar's buttons ended up with no names.

This module makes toolbar *composition* a plain data structure instead. The
``.ui`` keeps its job of defining the actions (including their icons and their
Designer-wired signal connections); the spec below decides which toolbar each
action appears on and in what order. Reordering is a one-line edit here rather
than a round trip through Designer and ``pyside6-uic``.

The actions themselves are reused, never recreated, so every connection made
in Designer survives.

Ordering follows how often things are actually used, rather than treating
everything as equally important:

* **Primary** -- the build/inspect loop you touch constantly.
* **Secondary** -- real but occasional: persistence and the renderers.
* **Demoted** -- still reachable from the menus, off the toolbar.

:data:`DEMOTED_ACTIONS` is not decoration. :func:`apply_toolbar_layout` checks
that every action which used to be on a toolbar is either placed by the spec
or named there, and raises if one is neither. Without that, dropping an action
from the spec would silently remove it from the UI.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt

if TYPE_CHECKING:
    from qiskit_metal._gui.main_window import MetalGUI

#: Icon edge length shared by every toolbar. The .ui shipped 24px implicitly
#: on one top toolbar and 32px hardcoded on the other, so they rendered at
#: different heights on the same row.
TOOLBAR_ICON_PX = 20

#: Separator marker inside a toolbar spec.
SEP = None

#: Toolbar object name -> ordered action object names. ``SEP`` inserts a
#: separator. Names are resolved against ``gui.ui``; an unknown name is an
#: error, not a silent skip.
TOOLBAR_LAYOUT = {
    # Top bar: the loop you live in. Rebuild first because it is the single
    # most-used control; refresh next to it since they are the same gesture.
    "toolBarDesign": [
        "actionRebuild",
        "action_full_refresh",
        SEP,
        # Persistence: real, but far less frequent than rebuilding.
        "actionSave",
        "actionLoad",
        SEP,
        # Created in code rather than the .ui; see MetalGUI.toggle_theme.
        "actionThemeToggle",
    ],
    # Renderers stay their own group so they read as "export/simulate"
    # rather than blending into the build controls.
    "toolbar_renderers": [
        "actionGDS",
        "actionHFSS",
        "actionQ3D",
    ],
}

#: Actions deliberately left off the toolbars, still available in the menus.
#: Each entry needs a reason -- this is the record of an intentional choice,
#: so a future reader can tell it apart from an accident.
DEMOTED_ACTIONS = {
    "actionBuildHistory": "Diagnostic; rarely consulted. Menu only.",
    "actionDelete_All": "Destructive and rare; menu only, where the "
    "confirmation dialog reads as deliberate.",
    "actionWebHelp": "One-off, not part of any working loop. Menu only.",
}


def _iter_spec_names():
    """Yield every action name the spec places, in declaration order."""
    for names in TOOLBAR_LAYOUT.values():
        for name in names:
            if name is not SEP:
                yield name


def _collect_existing_action_names(gui: "MetalGUI") -> set:
    """Return the action names currently sitting on the managed toolbars.

    Only the toolbars this module owns are inspected; the view toolbar and
    the plot toolbar are composed elsewhere and are not its business.
    """
    existing = set()
    for toolbar_name in TOOLBAR_LAYOUT:
        toolbar = getattr(gui.ui, toolbar_name, None)
        if toolbar is None:
            continue
        for action in toolbar.actions():
            if action.isSeparator():
                continue
            name = action.objectName()
            if name:
                existing.add(name)
    return existing


def check_no_actions_lost(gui: "MetalGUI", existing: set) -> None:
    """Fail loudly if an action would vanish from the UI.

    Args:
        gui (MetalGUI): The GUI being laid out.
        existing (set): Action names present on the managed toolbars before
            the layout was applied.

    Raises:
        RuntimeError: An action was on a toolbar but the new spec neither
            places it nor lists it in :data:`DEMOTED_ACTIONS`.
    """
    placed = set(_iter_spec_names())
    unaccounted = existing - placed - set(DEMOTED_ACTIONS)
    if unaccounted:
        raise RuntimeError(
            "Toolbar layout would drop these actions with no decision "
            f"recorded: {sorted(unaccounted)}. Either place them in "
            "TOOLBAR_LAYOUT or add them to DEMOTED_ACTIONS with a reason."
        )


def apply_toolbar_layout(gui: "MetalGUI") -> None:
    """Rebuild the managed toolbars from :data:`TOOLBAR_LAYOUT`.

    Existing ``QAction`` objects are reused, so the signal connections made
    in Qt Designer are preserved -- only placement and order change.

    Args:
        gui (MetalGUI): The GUI whose toolbars should be laid out.

    Raises:
        RuntimeError: The spec names an action that does not exist, or would
            drop one without a recorded decision.
    """
    existing = _collect_existing_action_names(gui)
    check_no_actions_lost(gui, existing)

    for toolbar_name, action_names in TOOLBAR_LAYOUT.items():
        toolbar = getattr(gui.ui, toolbar_name, None)
        if toolbar is None:
            continue

        toolbar.clear()

        for name in action_names:
            if name is SEP:
                toolbar.addSeparator()
                continue

            action = getattr(gui.ui, name, None)
            if action is None:
                raise RuntimeError(
                    f"TOOLBAR_LAYOUT references unknown action {name!r}. "
                    "Action names must match main_window_ui.ui."
                )
            toolbar.addAction(action)

        # One size and style for every managed toolbar, so they line up.
        # Text beside icon rather than under it: under-icon labels stack and
        # roughly double the bar's height.
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar.setIconSize(QSize(TOOLBAR_ICON_PX, TOOLBAR_ICON_PX))
        toolbar.setContentsMargins(0, 0, 0, 0)
        if toolbar.layout() is not None:
            toolbar.layout().setSpacing(2)
            toolbar.layout().setContentsMargins(2, 0, 2, 0)
