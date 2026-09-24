#!/usr/bin/env python3
"""
Generate the figures for the README from results/raw.jsonl.

Every chart here is computed from the run, never drawn by hand. A figure that
cannot be regenerated is a claim rather than evidence, and the whole point of
this repository is the difference between those two things.

Requires matplotlib, which is the only dependency in the project and is needed
only to redraw figures - the benchmark and both scorers are standard library.

    python3 tools/make_charts.py            -> docs/charts/*.png
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schema                                                      # noqa: E402
from score_results import PRICES, correct, predictions, scoreable   # noqa: E402

import matplotlib                                                   # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                     # noqa: E402

JEV = "#0E9594"      # teal
LLM = "#E07A5F"      # terracotta
INK = "#22223B"
MUTED = "#8D99AE"
GRID = "#E8E8EF"

plt.rcParams.update({
    "font.size": 12,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
})

LABEL = {"jev": "Jev 1.13", "llm": schema.LLM_LABEL}
COLOUR = {"jev": JEV, "llm": LLM}


def load(path):
    records = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
               if line.strip()]
    return [r for r in records if r.get("ok")]


def answers(records, model, scoreable_only=True):
    """Every answer as (confidence, was_correct).

    `scoreable_only` matters and is not cosmetic. Anything measuring ACCURACY
    must skip spam rows, which carry no true department, urgency or
    frustration. Anything measuring the model's OUTPUT BEHAVIOUR - how much of
    the confidence scale it actually uses - should count every answer it gave,
    including on those rows. Mixing the two produced two different counts of
    "distinct confidence values" for the same run."""
    out = []
    for r in records:
        if r["model"] != model:
            continue
        for field in schema.FIELDS:
            if scoreable_only and not scoreable(field, r):
                continue
            a = r["answers"].get(field) or {}
            conf = a.get("confidence")
            if conf is None:
                continue
            if scoreable_only:
                pred, _, _ = predictions(field, r)
                if pred is None:
                    continue
                out.append((float(conf), bool(correct(field, r, pred))))
            else:
                out.append((float(conf), None))
    return out


def style(ax, title, subtitle=None):
    ax.set_title(title, fontsize=15, fontweight="bold", loc="left", pad=18 if subtitle else 10)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=11, color=MUTED)
    ax.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------------------

def chart_reliability(records, out):
    """Stated confidence against measured accuracy. The diagonal is perfection."""
    bins = [(0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0), (1.0, 1.01)]
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot([0, 1], [0, 1], "--", color=MUTED, linewidth=1.5, zorder=1,
            label="perfectly calibrated")

    lowest = 1.0
    for model in ("jev", "llm"):
        data = answers(records, model)
        xs, ys, ns = [], [], []
        for lo, hi in bins:
            hit = [c for c in data if lo <= c[0] < hi]
            if len(hit) < 5:
                continue
            xs.append(statistics.mean(c[0] for c in hit))
            ys.append(sum(c[1] for c in hit) / len(hit))
            ns.append(len(hit))
        lowest = min([lowest] + ys)
        ax.plot(xs, ys, "-", color=COLOUR[model], linewidth=2.5,
                label=LABEL[model], zorder=3)
        # One dot per bucket, sized by how many answers landed in it. The
        # low-confidence buckets are genuinely noisy and the sizing is what
        # says so - dropping them to smooth the line would be choosing the
        # prettier picture over the true one.
        for x, y, n in zip(xs, ys, ns):
            ax.scatter([x], [y], s=max(50, min(500, n * 1.4)), color=COLOUR[model],
                       alpha=0.30, zorder=2)
            ax.scatter([x], [y], s=45, color=COLOUR[model], zorder=4)
            ax.annotate(f"n={n}", xy=(x, y), xytext=(0, 12 if model == "jev" else -20),
                        textcoords="offset points", fontsize=9, color=COLOUR[model],
                        ha="center")

    ax.set_xlabel("confidence the model reported")
    ax.set_ylabel("how often it was actually right")
    ax.set_xlim(0.3, 1.04)
    ax.set_ylim(max(0, lowest - 0.12), 1.06)
    ax.legend(frameon=False, loc="upper left")
    style(ax, "Does the confidence number mean anything?",
          "Below the dashed line is overconfidence. Dot size = answers in that bucket.")
    fig.tight_layout()
    fig.savefig(out / "reliability.png", dpi=200)
    plt.close(fig)


def chart_confidence_spread(records, out):
    """The strongest single image: one model uses the scale, the other doesn't."""
    fig, axes = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
    total = 0
    for ax, model in zip(axes, ("jev", "llm")):
        # scoreable_only=False: this chart is about how much of the scale the
        # model uses, which is a fact about its output, not about scoring.
        vals = [round(c, 2) for c, _ in answers(records, model, scoreable_only=False)]
        total = len(vals)
        counts = Counter(vals)
        ax.bar(list(counts.keys()), list(counts.values()), width=0.008,
               color=COLOUR[model], alpha=0.9)
        ax.set_ylabel("answers")
        ax.text(0.015, 0.86,
                f"{LABEL[model]} — {len(counts)} distinct values",
                transform=ax.transAxes, fontsize=14, fontweight="bold",
                color=COLOUR[model])
        top, n = counts.most_common(1)[0]
        # Text sits to the LEFT of the spike with the arrow pointing right at
        # it; centring it over the bar drew the arrow straight through the
        # words and read as a strikethrough.
        ax.annotate(f"{top:g} used {n}×", xy=(top, n), xytext=(-28, 0),
                    textcoords="offset points", fontsize=12, color=INK,
                    ha="right", va="center",
                    arrowprops=dict(arrowstyle="->", color=MUTED, linewidth=1.2))
        ax.set_ylim(0, n * 1.22)
        ax.grid(True, axis="y", color=GRID, linewidth=1)
        ax.set_axisbelow(True)

    axes[1].set_xlabel("confidence reported")
    axes[0].set_title("One of these models uses the confidence scale",
                      fontsize=16, fontweight="bold", loc="left", pad=20)
    axes[0].text(0, 1.04,
                 f"All {total} answers — 200 messages × four questions, both models.",
                 transform=axes[0].transAxes, fontsize=11, color=MUTED)
    fig.tight_layout()
    fig.savefig(out / "confidence-spread.png", dpi=200)
    plt.close(fig)


def chart_threshold(records, out):
    """What each routing threshold actually buys: automation against accuracy."""
    fig, ax = plt.subplots(figsize=(8, 6))
    for model in ("jev", "llm"):
        data = answers(records, model)
        xs, ys, ts = [], [], []
        for t in [i / 100 for i in range(50, 101, 5)]:
            auto = [c for c in data if c[0] >= t]
            if len(auto) < 20:
                continue
            xs.append(100 * len(auto) / len(data))
            ys.append(100 * sum(c[1] for c in auto) / len(auto))
            ts.append(t)
        ax.plot(xs, ys, "-o", color=COLOUR[model], linewidth=2.5, markersize=7,
                label=LABEL[model])
        # Offset the two series in opposite directions - both models hit
        # ≥0.90 at almost the same point and the labels landed on top of
        # each other.
        dy = 12 if model == "jev" else -18
        for x, y, t in zip(xs, ys, ts):
            if abs(t - 0.70) < 1e-9 or abs(t - 0.90) < 1e-9:
                ax.annotate(f"≥{t:.2f}", xy=(x, y), xytext=(8, dy),
                            textcoords="offset points", fontsize=11,
                            fontweight="bold", color=COLOUR[model])

    ax.set_xlabel("decisions handled automatically  (%)")
    ax.set_ylabel("accuracy of those decisions  (%)")
    ax.legend(frameon=False, loc="lower left")
    style(ax, "What each confidence threshold buys",
          "Up and to the right is better: more automated, and more often right.")
    fig.tight_layout()
    fig.savefig(out / "threshold-tradeoff.png", dpi=200)
    plt.close(fig)


def chart_headline(records, out):
    """Per-field accuracy, plus cost and latency. The win and the loss together."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 5), gridspec_kw={"width_ratios": [2.1, 1, 1]})

    ax = axes[0]
    fields, jv, lv = [], [], []
    for field in schema.FIELDS:
        rows = {m: [r for r in records if r["model"] == m and scoreable(field, r)]
                for m in ("jev", "llm")}
        if not rows["jev"]:
            continue
        fields.append(field)
        for model, bucket in (("jev", jv), ("llm", lv)):
            hits = sum(correct(field, r, predictions(field, r)[0]) for r in rows[model])
            bucket.append(100 * hits / len(rows[model]))
    x = range(len(fields))
    ax.bar([i - 0.2 for i in x], jv, width=0.4, color=JEV, label=LABEL["jev"])
    ax.bar([i + 0.2 for i in x], lv, width=0.4, color=LLM, label=LABEL["llm"])
    for i, (a, b) in enumerate(zip(jv, lv)):
        ax.text(i - 0.2, a + 1.5, f"{a:.0f}", ha="center", fontsize=10, color=INK)
        ax.text(i + 0.2, b + 1.5, f"{b:.0f}", ha="center", fontsize=10, color=INK)
    ax.set_xticks(list(x))
    ax.set_xticklabels(fields)
    ax.set_ylim(0, 110)
    ax.set_ylabel("accuracy  (%)")
    # Below the axis: every in-plot position collides with a bar, because two
    # of the four questions are answered at ~100% by both models.
    ax.legend(frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.09))
    style(ax, "Accuracy by question")

    def small(ax, values, title, fmt, ylabel):
        ax.bar([0, 1], values, width=0.55, color=[JEV, LLM])
        for i, v in enumerate(values):
            ax.text(i, v * 1.03, fmt.format(v), ha="center", fontsize=11, color=INK)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Jev", "GPT"])
        ax.set_ylim(0, max(values) * 1.25)
        ax.set_ylabel(ylabel)
        style(ax, title)

    costs = []
    for model in ("jev", "llm"):
        rows = [r for r in records if r["model"] == model]
        p = PRICES[model]
        tin = statistics.mean(r["usage"].get("input_tokens") or 0 for r in rows)
        tout = statistics.mean(r["usage"].get("output_tokens") or 0 for r in rows)
        costs.append((tin * p["in"] + tout * p["out"]) / 1e6 * 1000)
    small(axes[1], costs, "Cost per 1 000", "${:.3f}", "USD")

    lat = [statistics.median(r["ms"] for r in records
                             if r["model"] == m and not r.get("cold")) for m in ("jev", "llm")]
    small(axes[2], lat, "Warm latency", "{:.0f} ms", "milliseconds")

    fig.tight_layout()
    fig.savefig(out / "headline.png", dpi=200)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default="results/raw.jsonl")
    ap.add_argument("--out", default="docs/charts")
    args = ap.parse_args()

    records = load(args.raw)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for fn in (chart_reliability, chart_confidence_spread, chart_threshold, chart_headline):
        fn(records, out)
        print(f"  {fn.__name__}")
    print(f"\nwrote 4 charts to {out}/")


if __name__ == "__main__":
    main()
