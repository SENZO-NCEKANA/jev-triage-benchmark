#!/usr/bin/env python3
"""
Draw the explainer diagram: how a System One model changes what you can build.

Four panels, animated dashed connectors, written to both a GIF and a static PNG.

WHY A GIF
---------
LinkedIn animates GIFs in-feed and GitHub renders them in a README. Animated
SVG does neither reliably - GitHub sanitises SVG and drops CSS/SMIL animation
when it is referenced as an image.

The movement is the dash pattern sliding along each connector: matplotlib takes
a linestyle of (offset, (dash, gap)), and advancing `offset` each frame makes
the dashes flow. The offset wraps at exactly one dash period so the loop has no
visible jump.

NUMBERS
-------
Every figure is parsed out of the generated reports rather than typed in, the
same rule the rest of this repo follows. Re-run the benchmark and the diagram
follows. If a report is missing or its shape changes, the script says so and
stops rather than drawing a stale number.

    python3 tools/make_diagram.py
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib                                          # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                            # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter   # noqa: E402
from matplotlib.patches import FancyBboxPatch, Polygon     # noqa: E402

JEV = "#0E9594"
LLM = "#E07A5F"
INK = "#22223B"
MUTED = "#8D99AE"
AMBER = "#E9A03B"
RED = "#C1485A"

PANEL_FILLS = ["#EAF5F4", "#EFF1F8", "#F1F7EE", "#FBF0EC"]
PANEL_EDGES = ["#BFDEDB", "#C9CFE4", "#CBE0C2", "#EFCFC2"]

DASH = 9.0          # dash period in points; the offset wraps at this value
FRAMES = 36
FPS = 18


# ---------------------------------------------------------------------------
# Numbers, read from the generated reports
# ---------------------------------------------------------------------------

def read_facts(results):
    report = (results / "report.md")
    cascade = (results / "cascade.md")
    for f in (report, cascade):
        if not f.exists():
            sys.exit(f"{f} not found - run score_results.py and cascade_analysis.py first")

    facts = {}
    rt, cs = report.read_text(encoding="utf-8"), cascade.read_text(encoding="utf-8")

    # "| ≥ 0.70 |  89.1% | ** 95.7%** |  99.2% | ** 90.6%** |"  - jev is first
    row = re.search(r"\|\s*≥\s*0\.70\s*\|\s*([\d.]+)%\s*\|\s*\*\*\s*([\d.]+)%\*\*", rt)
    if not row:
        sys.exit("could not find the ≥0.70 threshold row in report.md")
    facts["auto_pct"], facts["auto_acc"] = float(row.group(1)), float(row.group(2))

    for key, pattern in (
        ("jev_alone", r"\|\s*Jev alone\s*\|\s*\*\*([\d.]+)%\*\*"),
        ("cascade", r"\|\s*Confidence-routed cascade[^|]*\|\s*([\d.]+)%"),
    ):
        m = re.search(pattern, cs)
        if not m:
            sys.exit(f"could not find '{key}' in cascade.md")
        facts[key] = float(m.group(1))

    m = re.search(r"for ([\d.]+)× the cost", cs)
    if not m:
        sys.exit("could not find the cascade cost multiple in cascade.md")
    facts["cascade_cost"] = float(m.group(1))
    return facts


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def box(ax, x, y, w, h, label, *, fill="white", edge=MUTED, fs=11,
        weight="normal", colour=INK, radius=0.03):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f"round,pad=0.008,rounding_size={radius}",
        facecolor=fill, edgecolor=edge, linewidth=1.6, zorder=2))
    ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
            fontsize=fs, color=colour, zorder=3, fontweight=weight,
            linespacing=1.45)


def diamond(ax, cx, cy, w, h, label):
    ax.add_patch(Polygon(
        [(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)],
        closed=True, facecolor="white", edgecolor=AMBER, linewidth=1.8, zorder=2))
    ax.text(cx, cy, label, ha="center", va="center", fontsize=10.5,
            color=INK, zorder=3, fontweight="bold")


def flow(ax, pts, colour=MUTED, lw=2.0):
    """A connector whose dashes will be animated. Returns the Line2D."""
    xs, ys = zip(*pts)
    (line,) = ax.plot(xs, ys, linestyle=(0, (4.5, 4.5)), color=colour,
                      linewidth=lw, zorder=1, solid_capstyle="round")
    # A small arrowhead at the final segment, drawn once and left static.
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="-|>", color=colour, linewidth=0,
                                mutation_scale=16), zorder=2)
    return line


def panel(fig, rect, index, title):
    ax = fig.add_axes(rect)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch(
        (0.004, 0.004), 0.992, 0.992,
        boxstyle="round,pad=0.004,rounding_size=0.02",
        facecolor=PANEL_FILLS[index], edgecolor=PANEL_EDGES[index],
        linewidth=2, zorder=0))
    ax.text(0.5, 0.935, title, ha="center", va="center", fontsize=13.5,
            fontweight="bold", color=INK, zorder=3,
            bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                      edgecolor=PANEL_EDGES[index], linewidth=1.4))
    return ax


# ---------------------------------------------------------------------------
# The four panels
# ---------------------------------------------------------------------------

def panel_typed(ax):
    """It answers questions. It does not write text."""
    lines = []
    box(ax, 0.03, 0.435, 0.185, 0.165, "Customer\nmessage", fill="white", fs=10)
    box(ax, 0.275, 0.405, 0.20, 0.225, "Jev\none call", fill="white",
        edge=JEV, fs=12, weight="bold", colour=JEV)
    lines.append(flow(ax, [(0.22, 0.518), (0.268, 0.518)]))

    answers = [
        ("department", "billing", "1.00"),
        ("urgency", "0.4", "0.86"),
        ("is_spam", "no", "0.97"),
        ("frustration", "1.0", "0.93"),
    ]
    # The confidence sits OUTSIDE the box to its right. An earlier version
    # right-aligned it at the panel edge, which put it on top of the label.
    top = 0.735
    for i, (name, value, conf) in enumerate(answers):
        y = top - i * 0.132
        box(ax, 0.545, y - 0.050, 0.30, 0.100,
            f"{name}  →  {value}", fill="white", edge=JEV, fs=8.5)
        ax.text(0.862, y, conf, ha="left", va="center",
                fontsize=8.5, color=MUTED, zorder=3)
        # Fan out from the Jev box rather than stubbing off the answer box -
        # the connector is the thing that animates, so it needs length.
        lines.append(flow(ax, [(0.48, 0.518), (0.515, y), (0.54, y)],
                          colour=JEV, lw=1.5))
    ax.text(0.862, top + 0.078, "conf", ha="left", va="center",
            fontsize=8, color=MUTED, style="italic")

    ax.text(0.5, 0.115, "Four typed answers with probabilities — no prose to parse",
            ha="center", va="center", fontsize=9.5, color=MUTED, style="italic")
    return lines


def panel_gate(ax):
    """Confidence is a gate, not a comment."""
    lines = []
    box(ax, 0.05, 0.47, 0.19, 0.15, "Answer\n+ confidence", fill="white", fs=9.5)
    diamond(ax, 0.44, 0.545, 0.24, 0.26, "≥ 0.70 ?")
    lines.append(flow(ax, [(0.245, 0.545), (0.315, 0.545)]))

    box(ax, 0.68, 0.655, 0.28, 0.14, "File it\nautomatically",
        fill="white", edge=JEV, fs=10, colour=JEV, weight="bold")
    box(ax, 0.68, 0.315, 0.28, 0.14, "Send it\nto a person",
        fill="white", edge=AMBER, fs=10, colour=AMBER, weight="bold")

    lines.append(flow(ax, [(0.565, 0.565), (0.63, 0.725), (0.675, 0.725)],
                      colour=JEV, lw=2.2))
    lines.append(flow(ax, [(0.565, 0.525), (0.63, 0.385), (0.675, 0.385)],
                      colour=AMBER, lw=2.2))
    ax.text(0.612, 0.775, "yes", fontsize=9, color=JEV, ha="center")
    ax.text(0.612, 0.325, "no", fontsize=9, color=AMBER, ha="center")

    ax.text(0.5, 0.11, "The model says how sure it is.\nYour code decides what that earns.",
            ha="center", va="center", fontsize=9.5, color=MUTED, style="italic")
    return lines


def panel_buys(ax, f):
    """What the threshold actually buys."""
    auto, human = f["auto_pct"], 100 - f["auto_pct"]
    bar_l, bar_r, y, h = 0.09, 0.91, 0.60, 0.13
    split = bar_l + (bar_r - bar_l) * auto / 100

    ax.add_patch(FancyBboxPatch((bar_l, y), split - bar_l, h,
                                boxstyle="round,pad=0,rounding_size=0.012",
                                facecolor=JEV, edgecolor="none", zorder=2))
    ax.add_patch(FancyBboxPatch((split, y), bar_r - split, h,
                                boxstyle="round,pad=0,rounding_size=0.012",
                                facecolor=AMBER, edgecolor="none", zorder=2))
    ax.text((bar_l + split) / 2, y + h / 2, f"{auto:.0f}% automatic",
            ha="center", va="center", fontsize=11, color="white",
            fontweight="bold", zorder=3)
    ax.text((split + bar_r) / 2, y + h / 2, f"{human:.0f}%",
            ha="center", va="center", fontsize=10, color="white",
            fontweight="bold", zorder=3)

    ax.text(bar_l, y + h + 0.075, "at a 0.70 threshold",
            fontsize=9.5, color=MUTED, ha="left")
    ax.text(0.5, 0.40, f"{f['auto_acc']:.1f}%", ha="center", va="center",
            fontsize=30, fontweight="bold", color=JEV)
    ax.text(0.5, 0.295, "of the automatic decisions were correct",
            ha="center", va="center", fontsize=10, color=INK)
    ax.text(0.5, 0.13, "The rest go to a human — which is what the\nconfidence number is genuinely good for.",
            ha="center", va="center", fontsize=9.5, color=MUTED, style="italic")
    return []


def panel_cascade(ax, f):
    """The escalation that doesn't work."""
    lines = []
    box(ax, 0.06, 0.60, 0.22, 0.14, "Not sure\n(low confidence)", fill="white",
        edge=AMBER, fs=9.5, colour=AMBER)

    box(ax, 0.575, 0.72, 0.385, 0.13, "Ask a person", fill="white",
        edge=JEV, fs=10.5, colour=JEV, weight="bold")
    box(ax, 0.575, 0.46, 0.385, 0.13, "Ask a bigger model", fill="white",
        edge=LLM, fs=10, colour=LLM, weight="bold")

    lines.append(flow(ax, [(0.285, 0.685), (0.47, 0.785), (0.57, 0.785)],
                      colour=JEV, lw=2.2))
    lines.append(flow(ax, [(0.285, 0.655), (0.47, 0.525), (0.57, 0.525)],
                      colour=LLM, lw=2.2))

    ax.text(0.405, 0.567, "✕", fontsize=26, color=RED, ha="center",
            va="center", zorder=4, fontweight="bold")

    ax.text(0.5, 0.315, f"{f['jev_alone']:.1f}%   →   {f['cascade']:.1f}%",
            ha="center", va="center", fontsize=17, fontweight="bold", color=INK)
    ax.text(0.5, 0.235, f"accuracy went DOWN, at {f['cascade_cost']:.1f}× the cost",
            ha="center", va="center", fontsize=10, color=RED)
    ax.text(0.5, 0.10,
            "Confidence measures this answer's own spread.\nIt cannot know another model would do better.",
            ha="center", va="center", fontsize=9.5, color=MUTED, style="italic")
    return lines


# ---------------------------------------------------------------------------

def build(facts):
    fig = plt.figure(figsize=(11, 11.6), facecolor="white")
    fig.text(0.5, 0.965, "Typed decisions, not text",
             ha="center", fontsize=25, fontweight="bold", color=INK)
    fig.text(0.5, 0.936,
             "What a calibrated confidence score changes — measured over 200 labelled messages",
             ha="center", fontsize=11.5, color=MUTED)

    w, h, gap = 0.445, 0.395, 0.025
    left, right = 0.035, 0.52
    bottom, top = 0.055, 0.495

    specs = [
        ((left, top, w, h), 0, "1) One call, four typed answers", panel_typed, None),
        ((right, top, w, h), 1, "2) Confidence is a gate", panel_gate, None),
        ((left, bottom, w, h), 2, "3) What the gate buys", panel_buys, facts),
        ((right, bottom, w, h), 3, "4) The escalation that fails", panel_cascade, facts),
    ]
    lines = []
    for rect, idx, title, fn, arg in specs:
        ax = panel(fig, rect, idx, title)
        lines += fn(ax, arg) if arg is not None else fn(ax)

    fig.text(0.5, 0.022, "github.com/SENZO-NCEKANA/jev-triage-benchmark",
             ha="center", fontsize=9.5, color=MUTED)
    _ = gap
    return fig, lines


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default="docs/charts")
    args = ap.parse_args()

    facts = read_facts(Path(args.results))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    fig, lines = build(facts)
    fig.savefig(out / "how-it-works.png", dpi=150)

    def frame(i):
        # Negative offset makes the dashes travel forwards along the line.
        offset = -(i / FRAMES) * DASH
        for line in lines:
            line.set_linestyle((offset, (4.5, 4.5)))
        return lines

    # 110 dpi on an 11in figure gives ~1210px wide. LinkedIn renders feed
    # images around 1200px, and anything narrower gets upscaled and looks soft.
    anim = FuncAnimation(fig, frame, frames=FRAMES, interval=1000 / FPS, blit=False)
    anim.save(out / "how-it-works.gif", writer=PillowWriter(fps=FPS), dpi=110)
    plt.close(fig)

    for name in ("how-it-works.png", "how-it-works.gif"):
        size = (out / name).stat().st_size / 1e6
        print(f"  {out / name}  {size:.2f} MB")
    print("\nNow open both and look at them before using either.")


if __name__ == "__main__":
    main()
