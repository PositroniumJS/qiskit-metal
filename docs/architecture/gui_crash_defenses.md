# MetalGUI crash defenses — read before touching GUI startup or teardown

Issue [#1048](https://github.com/qiskit-community/qiskit-metal/issues/1048) and
its descendants took five releases, several PRs, and a lot of reporter testing
on hardware none of the maintainers own. The defenses that came out of it look
like scattered defensive noise if you meet them cold, and several of them look
removable. They are not.

**Read this file before changing anything in `_gui/` startup, teardown,
stylesheet handling, or persisted window state.** Then read the source
comments, which carry the per-line detail.

---

## The failure modes

Four distinct bugs wore the same shirt ("MetalGUI segfaults"). Telling them
apart is most of the work.

| # | Failure | Status |
|---|---------|--------|
| 1 | **At-exit teardown segfault.** `Py_FinalizeEx` destroys `QApplication` while the window is alive; `~QWidget` dispatches an event through a half-deleted `QMenuBar::eventFilter` into a null vtable. | Fixed, v0.7.4 (PR #1104) |
| 2 | **On-screen init crash at `show()`.** Root cause was **persisted-state corruption**, not the GPU. Stale `QSettings` geometry replayed into `show()`. On Windows: `0xC0000409 STATUS_STACK_BUFFER_OVERRUN` / `FAST_FAIL_FATAL_APP_EXIT` inside `ucrtbase.dll`. | Fixed, v0.7.5–v0.7.6 (PRs #1122, #1128, #1129) |
| 3 | **Cross-kernel restore crash.** Kernel A saves a layout, kernel B restores it under a changed display config. `restoreState()` does *not* raise, so a try/except never fires. | Fixed, v0.7.6 (PR #1128) |
| 4 | **Mid-session GC teardown segfault.** Same null-vtable mechanism as (1) but triggered by ordinary garbage collection, which `atexit` never covers. | **Open.** Nondeterministic — a 32-variant sweep crashed 16/32 once, then ran clean 10× at the same commit. Consistent with heap corruption. |

The GPU theory for (2) was **explicitly falsified**: the reporter got 0/5 with
`QT_OPENGL=software` after normal usage, then a clean pass after deleting the
registry key. Don't re-derive it.

---

## The defenses, and what each guards

### Persisted-state invalidation — `restore_window_settings`

Five checks, **in this order**, each clearing settings and returning:

1. `QISKIT_METAL_RESET_UI_SETTINGS=1` — user escape hatch
2. `metal_version` newer than saved — cross-version state
3. `qt_version` mismatch — Qt has no version tag on its own state blob
4. `display_fingerprint` mismatch — monitor hot-swap, DPI change, undock
5. `restore_in_progress` cookie found set — the previous launch crashed

Then it sets the cookie and `sync()`s **before** `restoreGeometry`/
`restoreState`. Any exception clears settings.

`_display_fingerprint()` is `name:x,y,w,h@dpr` per screen. It returns `""` on
error, and an empty value on either side short-circuits to a plain restore.

The `metal_version` check compares **parsed versions**, not strings. It was a
string compare until 2026-08-07 — correct only while every component stays
single-digit, since `'0.10.0' > '0.9.0'` is `False`. From v0.10.0 the guard
would have stopped firing with no error and no symptom: a defense quietly
switched off, and pre-0.10 layouts restored into a newer GUI. Any doubt now
resolves to "newer", because discarding state that might have been fine is the
cheap failure and restoring state that is not is the expensive one.

This guard doubles as the mechanism that gives users **new layout defaults on
upgrade**. Changing a dock's default visibility needs no migration code: the
saved layout is discarded on the version bump anyway. Worth knowing before
writing one.

### The crash cookie — the ordering constraint that matters most

`restore_in_progress` is set before the risky sequence and cleared **only by
`mark_startup_complete()`, after `main_window.show()` returns**.

The first implementation cleared it right after `restoreState()` returned.
That was a real bug, caught by CI on macOS (PR #1129, fixed in `a04ab68`):
the actual crash site is `show()`, well after `restoreState()`, and a native
abort there leaves no Python exception. Clearing early erases the one on-disk
signal that lets the next launch self-heal.

**Never narrow the cookie window.**

### Windows software OpenGL

`src/qiskit_metal/__init__.py` sets `QT_OPENGL=software` on `os.name == "nt"`
**before any PySide6 import**. Opt out with `QISKIT_METAL_QT_HARDWARE_GL=1`.

It must be the environment variable, not `Qt.AA_UseSoftwareOpenGL`: the
attribute is only a *hint*, read at `QGuiApplication` construction, and was
observed being silently ignored on the affected driver.

### Teardown

`_teardown_qt_widgets` runs via `atexit`, using `deleteLater()` — never
`close()`, which triggers the "save unsaved changes?" modal and blocks forever
headless.

### Bisection toggles

These exist so a reporter can bisect a native crash without a debugger. Keep
them working:

| Variable | Effect |
|---|---|
| `QISKIT_METAL_DEBUG_INIT=1` | Trace each init step to stderr, flushed. Last line = failing call. |
| `QISKIT_METAL_GUI_NO_STYLESHEET=1` | Skip the stylesheet (it affects every paint). |
| `QISKIT_METAL_GUI_NO_PLOT=1` | Skip the matplotlib canvas embed. |
| `QISKIT_METAL_RESET_UI_SETTINGS=1` | Start from clean persisted state. |
| `QISKIT_METAL_QT_HARDWARE_GL=1` | Undo the Windows software-GL default. |
| `QISKIT_METAL_GUI_FORCE_CLOSE=1` | Sets `main_window.force_close = True` at construction, so any `gui.main_window.close()` call skips `ok_to_close()`'s modal instead of hanging headless (see Teardown, above). Some frozen-Qt tutorial notebooks call `close()` as their last cell to demo the API; `_dev/rerun_auto.py` sets this for its `--write-frozen` Qt-display runs. Never set it for an interactive session — the modal is correct there. |

---

## Traps — changes that look safe and are not

- **`deleteLater()` is a false positive as a teardown fix.** It zeroes the
  crash in any test with no subsequent event loop, because the deletion never
  happens. Verify with `app.exec()`, never `processEvents()`. Seven candidate
  fixes were falsified this way; the table is in
  `tests/test_gui_logger_lifecycle.py`.

- **Moving the stylesheet load out of `restore_window_settings`.** Attempted
  2026-08-07 and reverted. The theme is genuinely skipped on all five
  early-return paths, so a fresh profile opens unstyled — a real, if cosmetic,
  bug. But applying it unconditionally turned `tests/test_gui_init.py` and
  `tests/test_gui_teardown.py` from 5 passed to 5 failed with `SIGBUS`. The
  early returns were accidentally protecting a known crash trigger. If this is
  revisited it needs the theme applied *inside* the cookie window and proof on
  Windows and Linux, not just macOS.

- **Log handlers must detach on `destroyed`, not `closeEvent`.** `close()`
  only hides; detaching there left a permanently dead log pane (reverted in
  `80f3655`).

- **Don't mark the GC reproducer `expectedFailure`** — it yields flaky
  "unexpected success". It is `@unittest.skip`ped deliberately.

- **A single clean run proves nothing** in either direction. The crash depends
  on memory layout.

- **Rejected outright in #1128:** disabling layout persistence on Windows,
  per-PID registry keys (breaks Jupyter), writer-PID detection (stale locks).

- **Check `qiskit_metal.__version__` in every report.** Two "still broken"
  reports were on 0.5.3.post1 and a 0.7.3 fork — neither had the fixes.

---

## Cross-platform reality

- The exit segfault (1) reproduces on Linux/Xvfb.
- The Windows `show()` crash (2) never reproduced under Xvfb or on GitHub
  Windows runners — runners start with an empty registry, which is exactly the
  state that works.
- macOS CI is what caught the cookie-scope gap.
- PySide6 version is **not** implicated: 6.6.0, 6.8.3 and 6.10.1 behave
  identically on the dangling-wrapper probe.

Consequence: **CI passing does not mean the crash is fixed.** Reporter
confirmation on the affected hardware is the only real signal, and that is how
v0.7.5 and v0.7.6 were validated (6/6 clean, then clean in JupyterLab and
VS Code with no fallbacks).

---

## Tests and the guarantee each encodes

`tests/test_gui_teardown.py`
- `test_metalgui_process_exits_cleanly` — builds a GUI, a second GUI, and
  `rebuild()` in a subprocess; asserts marker + exit code 0. Was `-11` before
  PR #1104.

`tests/test_gui_init.py` — each runs a real save subprocess, tampers exactly
one field, then re-reads on-disk state to prove the *correct* branch fired:
- `test_metalgui_init_completes` — marker catches silent abandonment, return
  code catches segfault.
- `test_metalgui_init_self_heals_across_kernel_switch` — the A→B→C kernel
  sequence. B may crash; C must always build.
- `test_metalgui_init_with_stale_fingerprint` — the display-fingerprint branch.
- `test_metalgui_init_recovers_from_crashed_restore` — the cookie branch.

`tests/test_gui_logger_lifecycle.py` — handler leaks, timer lifecycle, and the
skipped `test_dropping_metalgui_does_not_segfault`, which carries the gdb
backtrace and the falsified-candidate table as living documentation of
failure mode (4).

CI: `tests-gui-display` (Linux Xvfb) and `tests-gui-display-windows`
(`windows-2025`, `continue-on-error: true`).

---

## Still open

- Failure mode (4), the GC teardown segfault, on all versions.
- Whether the macOS `show()` → `QLayout::activate()` crash reported against a
  0.7.3 fork is resolved on 0.8.0 — the reporter never confirmed.
- **New, minor:** `tests/test_gui_nudge.py::TestRealClickAndKeyDelivery` --
  the one test that drives a real MetalGUI through several genuine Qt
  click/key/rebuild cycles (`QTest`-injected, not `_on_pick_release()`
  called directly) -- occasionally leaves `QTreeModel_Base.auto_refresh()`'s
  polling `QTimer` alive past `close()`, and it fires during **pytest's own
  process exit**, well after the whole suite already reported passing:
  `RuntimeError: Internal C++ object (PySide6.QtWidgets.QCompleter) already
  deleted`. Exit code stays 0 either way (confirmed reproducible on/off by
  including/excluding just that one test, several repeats). Explicitly did
  **not** attempt a real fix here -- an attempted test-side workaround
  (pumping `app.processEvents()` after `close()` to flush queued
  `deleteLater()` teardown before the test function returns) made it
  *worse*, occasionally turning the exit code non-zero, so it was reverted.
  Left as class-(4)-adjacent noise for a future, more careful pass rather
  than guessed at under time pressure.
