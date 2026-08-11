"""Generate the movement/rotate diagrams for the GUI shortcuts docs page.

These illustrate the keyboard shortcuts bound in
``renderers/renderer_mpl/mpl_canvas.py`` (``_NUDGE_DIRECTIONS``,
``_ROTATE_DIRECTIONS``) -- a diagram is faster to parse than a table of
key names for "which way does this go."

USAGE
-----

  uv run python _dev/generate_gui_shortcut_diagrams.py --write

Idempotent: re-running with ``--write`` overwrites the SVGs (this script
is the source of truth for them, same convention as
``generate_scaffold_icons.py``). Outputs are tracked files, not built on
every docs build -- there's no runtime data to go stale, only re-run
this by hand if the bindings themselves change.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Arc, FancyArrow, FancyArrowPatch

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "docs" / "images" / "gui-shortcuts"

# Matches badge_icon_alert's ERROR_ALERT_COLOR family / the dark-theme
# palette used for the notebook screenshots, so the diagrams don't clash
# visually with the rest of the docs.
ACCENT = "#3D8BFD"
INK = "#2b2b2b"
FAINT = "#8a8a8a"

# The docs theme has a light/dark toggle, but these are plain rasterized
# diagrams -- INK on a transparent background reads fine on the light
# theme and is nearly invisible on the dark one. Rather than track the
# page theme, give each diagram its own opaque light card so contrast is
# guaranteed regardless of what's around it (the same trick sphinx-design
# cards use).
CARD = "#f5f5f7"
CARD_EDGE = "#e0e0e3"


def _add_card(ax, xlim, ylim):
    from matplotlib.patches import FancyBboxPatch

    pad = 0.12
    ax.add_patch(
        FancyBboxPatch(
            (xlim[0] + pad, ylim[0] + pad),
            (xlim[1] - xlim[0]) - 2 * pad,
            (ylim[1] - ylim[0]) - 2 * pad,
            boxstyle="round,pad=0,rounding_size=0.18",
            linewidth=1.2,
            edgecolor=CARD_EDGE,
            facecolor=CARD,
            zorder=-10,
        )
    )


def _keycap(ax, x, y, label, *, size=0.34, fontsize=13):
    """Draw a small rounded-rect keycap, matching the Help dialog's
    ``_kbd()`` chip styling so the docs page and the in-app dialog read
    as the same visual language."""
    from matplotlib.patches import FancyBboxPatch

    box = FancyBboxPatch(
        (x - size, y - size * 0.7),
        size * 2,
        size * 1.4,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        linewidth=1.4,
        edgecolor=INK,
        facecolor="white",
    )
    ax.add_patch(box)
    ax.text(x, y, label, ha="center", va="center", fontsize=fontsize, color=INK)


def make_move_diagram(path: Path):
    """Arrow-key move pad: four directions around the selected component,
    with the Shift/Alt step modifiers called out underneath."""
    fig, ax = plt.subplots(figsize=(4.2, 4.2))
    ax.set_xlim(-2.2, 2.2)
    ax.set_ylim(-2.4, 2.2)
    ax.axis("off")
    ax.set_aspect("equal")
    _add_card(ax, ax.get_xlim(), ax.get_ylim())

    # The selected component, center.
    ax.add_patch(
        plt.Circle((0, 0), 0.42, facecolor=ACCENT, edgecolor="none", alpha=0.25)
    )
    ax.add_patch(plt.Circle((0, 0), 0.42, facecolor="none", edgecolor=ACCENT, lw=2))
    ax.text(0, 0, "selected", ha="center", va="center", fontsize=9, color=INK)

    directions = {
        "up": ((0, 0.55), (0, 1.35), "↑"),
        "down": ((0, -0.55), (0, -1.35), "↓"),
        "left": ((-0.55, 0), (-1.35, 0), "←"),
        "right": ((0.55, 0), (1.35, 0), "→"),
    }
    for start, end, glyph in directions.values():
        arrow = FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=18,
            linewidth=2.2,
            color=INK,
        )
        ax.add_patch(arrow)
        kx, ky = end[0] * 1.28, end[1] * 1.28
        _keycap(ax, kx, ky, glyph)

    ax.text(
        0,
        -2.05,
        "Shift = coarser step   ·   Alt = finer step",
        ha="center",
        va="center",
        fontsize=10,
        color=FAINT,
    )
    fig.tight_layout()
    fig.savefig(path, transparent=True)
    plt.close(fig)


def make_rotate_diagram(path: Path):
    """Rotate diagram: a curved arrow each way around the selected
    component, labelled with the step size and the keys that trigger it."""
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.set_xlim(-2.4, 2.4)
    ax.set_ylim(-2.2, 2.2)
    ax.axis("off")
    ax.set_aspect("equal")
    _add_card(ax, ax.get_xlim(), ax.get_ylim())

    ax.add_patch(
        plt.Circle((0, 0), 0.42, facecolor=ACCENT, edgecolor="none", alpha=0.25)
    )
    ax.add_patch(plt.Circle((0, 0), 0.42, facecolor="none", edgecolor=ACCENT, lw=2))
    ax.text(0, 0, "selected", ha="center", va="center", fontsize=9, color=INK)

    # Counter-clockwise arc (Q / [ ), left side.
    ccw = Arc((0, 0), 2.4, 2.4, angle=0, theta1=110, theta2=250, lw=2.2, color=INK)
    ax.add_patch(ccw)
    ax.add_patch(
        FancyArrow(-0.95, 1.13, -0.28, 0.14, width=0.02, head_width=0.14, color=INK)
    )
    _keycap(ax, -1.7, 0, "Q", size=0.3, fontsize=12)
    ax.text(-1.7, -0.55, "(also [ )", ha="center", fontsize=8, color=FAINT)

    # Clockwise arc (E / ] ), right side.
    cw = Arc((0, 0), 2.4, 2.4, angle=0, theta1=-70, theta2=70, lw=2.2, color=INK)
    ax.add_patch(cw)
    ax.add_patch(
        FancyArrow(0.95, 1.13, 0.28, 0.14, width=0.02, head_width=0.14, color=INK)
    )
    _keycap(ax, 1.7, 0, "E", size=0.3, fontsize=12)
    ax.text(1.7, -0.55, "(also ] )", ha="center", fontsize=8, color=FAINT)

    ax.text(
        0,
        -2.0,
        "90° per press   ·   hold Shift for a 15° step",
        ha="center",
        va="center",
        fontsize=10,
        color=FAINT,
    )
    fig.tight_layout()
    fig.savefig(path, transparent=True)
    plt.close(fig)


DIAGRAMS = {
    "move.svg": make_move_diagram,
    "rotate.svg": make_rotate_diagram,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the SVGs to docs/images/gui-shortcuts/",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, make in DIAGRAMS.items():
        out_path = OUT_DIR / filename
        if args.write:
            make(out_path)
            print(f"wrote {out_path.relative_to(REPO)}")
        else:
            print(f"(dry run) would write {out_path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
