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
"""This is a utility module used for qt."""

from types import MethodType

# from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDockWidget

__all__ = ["blend_colors"]


def blend_colors(color1: QColor, color2: QColor, r: float = 0.2, alpha=255) -> QColor:
    """Blend two qt colors together.

    Args:
        color1 (QColor): first color
        color2 (QColor): second color
        r (float): ratio
        alpha (int): alpha

    Returns:
        QColor: new color
    """
    color3 = QColor(
        color1.red() * (1 - r) + color2.red() * r,
        color1.green() * (1 - r) + color2.green() * r,
        color1.blue() * (1 - r) + color2.blue() * r,
        alpha,
    )
    return color3


# ------------------------------------------------------------------------------------------

# Qt stylesheets cascade: a rule set on a widget also matches every
# descendant that satisfies the selector. A bare ``QWidget { border: ... }``
# therefore outlined the widget *and* every child -- clicking Refresh
# red-boxed all the toolbars and icons inside the main view, not just the
# view. Scope by object name so only the target widget matches.
STYLE_HIGHLIGHT_TEMPLATE_ = "QWidget#{name} {{ border: 3px solid red; }}"

# Fallback object name for a target that has none, so the scoped selector
# above still has something to bind to.
_HIGHLIGHT_FALLBACK_NAME = "metalHighlightTarget"


def doShowHighlighWidget(self: QDockWidget, timeout=1500, style_highlight=None):
    """Highlight temporarily, raise, show the widget.
    Force resets the style at the component to None after a period.

    The highlight is scoped to this widget by object name; it does not
    outline child widgets.
    """
    if style_highlight is None:
        if not self.objectName():
            self.setObjectName(_HIGHLIGHT_FALLBACK_NAME)
        style_highlight = STYLE_HIGHLIGHT_TEMPLATE_.format(name=self.objectName())
    self.setStyleSheet(style_highlight)
    self.show()
    self.raise_()

    def doResetStyle(self: "QDockWidget"):
        """Reset the style of the widget."""
        self.setStyleSheet("")

    # Bind the method dynamically to the instance using MethodType
    self.doResetStyle = MethodType(doResetStyle, self)

    # self.doResetStyle = doResetStyle.__get__(self, type(self))
    # monkey patch class instance:
    # https://stackoverflow.com/questions/28127874/monkey-patching-python-an-instance-method

    QTimer.singleShot(timeout, self.doResetStyle)


def doToggleDockWidget(self: QDockWidget, timeout=1500, style_highlight=None):
    """Toggle-aware dock-raise: hide the dock if its icon is clicked while
    it is the one actually on screen, otherwise show/raise/highlight it
    like ``doShowHighlighWidget``.

    Works for tabified docks too, unlike a plain ``isVisible()`` check:
    every dock in a tabified group reports ``isVisible() == True`` once the
    group itself is shown, regardless of which tab is on top, because
    ``isVisible()`` doesn't know about the obscuring siblings. A dock that
    is tabified-but-not-the-active-tab has an *empty* ``visibleRegion()``
    (fully covered by whichever sibling is showing) even though
    ``isVisible()`` is True -- that combination is what distinguishes
    "raise/switch to this tab" from "this tab is already the one showing,
    so hide it."
    """
    currently_on_top = self.isVisible() and not self.visibleRegion().isEmpty()
    if currently_on_top:
        self.hide()
        return
    doShowHighlighWidget(self, timeout=timeout, style_highlight=style_highlight)


### Alternative to doShowHighlighWidget:

# from PySide6.QtWidgets import QFrame, QWidget
# from PySide6 import QtCore
# obj = gui.canvas
# frame = QFrame(obj.parent())
# frame.setGeometry(obj.frameGeometry())
# frame.setFrameShape(QFrame.Box)
# frame.setLineWidth(3)
# frame.show()

# frame.setStyleSheet(r"""
#   border-radius: 10px;
#   outline: 3px solid red;
#   border: 3px solid red;
#   background-color: transparent;
#   border-image:none;
# """)
# ## the folloing make it dissapear altoheger
# # frame.setWindowFlags(QtCore.Qt.FramelessWindowHint)
# # frame.setAttribute(QtCore.Qt.WA_TranslucentBackground)

# # Alternative see:
# https://stackoverflow.com/questions/58458323/how-to-use-qt-stylesheet-to-customize-only-partial-qwidget-border

# ------------------------------------------------------------------------------------------
