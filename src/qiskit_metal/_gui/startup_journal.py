# This code is part of Quantum Metal.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
"""Crash journal for MetalGUI startup (issue #1048).

A plain flag file, written and fsync'd as the *first* action of
``MetalGUI.__init__`` and removed only after the whole startup sequence --
including ``main_window.show()`` -- has completed. If a launch dies
anywhere in between (native Qt crash, killed process, power loss), the
file survives; the next launch sees it, wipes the persisted UI state, and
starts from pristine defaults instead of replaying whatever poisoned it.

This replaces the earlier ``restore_in_progress`` QSettings crash-cookie,
which had two structural holes CI actually hit:

1. **Coverage.** The cookie was set inside ``restore_window_settings()``,
   partway through init. A crash *before* that point -- QPA platform-plugin
   init, early widget construction -- left no cookie, so the next launch
   replayed the same crash. The journal opens at the first Python
   instruction of ``__init__``, before Qt is touched, so no crash in the
   protected window can escape it.
2. **Durability.** ``QSettings.sync()`` is not a synchronous disk barrier
   on every platform (macOS routes through the ``cfprefsd`` daemon, which
   flushes asynchronously); a native crash right after ``sync()`` could
   lose the cookie write. This file is written with ``flush()`` +
   ``os.fsync()`` -- a real barrier -- and "the file exists" is the whole
   protocol, so there is no parse step to get wrong.

Kept free of any Qt import on purpose: it must be usable before the
QApplication exists and must not itself depend on the machinery it guards.
"""

import os
from pathlib import Path

__all__ = [
    "begin_startup",
    "complete_startup",
    "journal_path",
    "previous_startup_crashed",
]


def journal_path() -> Path:
    """Location of the startup journal flag file.

    Under the user's home rather than a temp dir: temp dirs can be wiped
    between sessions by the OS, which would erase the one signal a crashed
    launch leaves behind.
    """
    return Path.home() / ".quantum-metal" / "gui_startup.journal"


def previous_startup_crashed() -> bool:
    """True if the last MetalGUI launch died before completing startup."""
    try:
        return journal_path().exists()
    except OSError:  # pragma: no cover - unreadable home dir
        return False


def begin_startup() -> None:
    """Open the protected window: write and fsync the flag file.

    Called first thing in ``MetalGUI.__init__``. Failure to write (read-only
    home, quota) is swallowed -- the journal is a safety net, and refusing
    to start the GUI because the net can't be hung would be backwards.
    """
    try:
        path = journal_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            file.write(f"pid={os.getpid()}\n")
            file.flush()
            os.fsync(file.fileno())
    except OSError:  # pragma: no cover - best-effort safety net
        pass


def complete_startup() -> None:
    """Close the protected window: remove the flag file.

    Called after ``main_window.show()`` has returned without crashing.
    """
    try:
        journal_path().unlink(missing_ok=True)
    except OSError:  # pragma: no cover - best-effort cleanup
        pass
