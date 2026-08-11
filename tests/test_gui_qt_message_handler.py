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

"""``_qt_message_handler`` only attaches a Python traceback to CRITICAL/FATAL
Qt messages.

Qt's own INFO/WARNING output includes routine, harmless notices (font-alias
population cost, missing-plugin capability notices, ...). Attaching a
10-frame traceback to every one of those made a benign log line
indistinguishable at a glance from a real crash report -- confirmed by a
user pasting one after clicking an ordinary toolbar button, not because
anything actually broke.
"""

import logging
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6")

# pylint: disable=wrong-import-position
from PySide6 import QtCore  # noqa: E402

from qiskit_metal._gui.utility import _handle_qt_messages as handler_module  # noqa: E402


class _RecordingLogger:
    """Stands in for ``qiskit_metal.logger`` to inspect what got logged."""

    def __init__(self):
        self.records = []

    def log(self, level, message):
        self.records.append((level, message))


@pytest.fixture(name="recording_logger")
def recording_logger_fixture(monkeypatch):
    """Swap in a recorder so no assertion depends on the real log format."""
    fake = _RecordingLogger()
    monkeypatch.setattr(handler_module, "logger", fake)
    return fake


def _context_without_source_info():
    """A Qt message context with no file/function -- the common case for
    messages that originate inside Qt itself rather than qiskit_metal."""
    context = MagicMock()
    context.file = None
    context.function = None
    return context


@pytest.mark.parametrize(
    "qt_mode",
    [
        QtCore.QtMsgType.QtDebugMsg,
        QtCore.QtMsgType.QtInfoMsg,
        QtCore.QtMsgType.QtWarningMsg,
    ],
)
def test_routine_messages_have_no_traceback(recording_logger, qt_mode):
    """DEBUG/INFO/WARNING are routine Qt chatter -- no stack dump."""
    handler_module._qt_message_handler(
        qt_mode,
        _context_without_source_info(),
        "Populating font family aliases took 149 ms.",
    )

    _level, message = recording_logger.records[-1]
    assert "Traceback" not in message


@pytest.mark.parametrize(
    "qt_mode",
    [QtCore.QtMsgType.QtCriticalMsg, QtCore.QtMsgType.QtFatalMsg],
)
def test_severe_messages_include_a_traceback(recording_logger, qt_mode):
    """CRITICAL/FATAL are the messages this handler exists to help
    diagnose -- keep the call-stack context for those."""
    handler_module._qt_message_handler(
        qt_mode, _context_without_source_info(), "something actually went wrong"
    )

    _level, message = recording_logger.records[-1]
    assert "Traceback" in message


def test_the_message_text_itself_always_survives(recording_logger):
    """Whatever else changes, the actual Qt message must still be logged."""
    handler_module._qt_message_handler(
        QtCore.QtMsgType.QtWarningMsg,
        _context_without_source_info(),
        "a distinctive warning text",
    )

    _level, message = recording_logger.records[-1]
    assert "a distinctive warning text" in message


def test_duplicate_socket_notifier_warning_is_suppressed(recording_logger):
    """A known-benign warning from re-running ``%gui qt`` -- logging it
    at all would be noise on every notebook re-run, not just the first."""
    handler_module._qt_message_handler(
        QtCore.QtMsgType.QtWarningMsg,
        _context_without_source_info(),
        "QSocketNotifier: Multiple socket notifiers for same socket 7 and type Read",
    )

    assert recording_logger.records == []
