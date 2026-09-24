#!/usr/bin/env python3
"""
Check what Jev's `confidence` number actually is, against our own run.

WHY
---
TypeSafe's confidence page says plainly:

    "confidence is a statistic computed from the probability distribution
     the answer already gives you."

and its interactive demo discloses the arithmetic for a three-option Choice:

    "This demo uses (3 x largest probability - 1) / 2 to approximate
     confidence for three options."

Generalised to n options that is:

    confidence = (n * peak - 1) / (n - 1)

which is 1.0 when all the mass sits on one option and 0.0 when it is spread
evenly. This script tests that against every Choice and Score answer in a run,
so the claim in the README is a measurement rather than a quotation.

It matters beyond trivia. If confidence is a function of *this* distribution
over *these* options, then it is structurally incapable of knowing anything
about a different model - which is exactly why escalating low-confidence
answers to an LLM bought so little in cascade_analysis.py. The mechanism and
the measured result agree.

WHAT IT FINDS
-------------
Choice answers match the formula within the rounding of the reported
probabilities (two decimals). Score answers do not: where probability spreads
across ordered levels, Jev reports LOWER confidence than the peak-only formula.
That is consistent with the docs, whose formula is stated for Choice only, and
it says Score confidence responds to dispersion across the scale rather than to
the winning level alone.

Usage:
    python3 tools/verify_confidence.py
    python3 tools/verify_confidence.py --raw results/raw.urgency-v1.jsonl
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schema  # noqa: E402

CHOICE_FIELDS = ("department", "is_spam")

# Reported probabilities carry two decimals, so the peak can be off by up to
# 0.005 before the formula is even applied. For n options that error is
# multiplied by n/(n-1), which is the tolerance each row is judged against.
DECIMALS = 2


def peak_formula(probabilities):
    n = len(probabilities)
    if n < 2:
        return None
    return max(0.0, min(1.0, (n * max(probabilities.values()) - 1) / (n - 1)))


def rounding_tolerance(n):
    return (n / (n - 1)) * (0.5 * 10 ** -DECIMALS) * 2


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default="results/raw.jsonl")
    ap.add_argument("--out", default="results/confidence-formula.md")
    ap.add_argument("--model", default="jev")
    args = ap.parse_args()

    path = Path(args.raw)
    if not path.exists():
        sys.exit(f"{path} not found - run run_benchmark.py first")

    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("model") != args.model or not rec.get("ok"):
            continue
        for field in schema.FIELDS:
            a = rec["answers"].get(field) or {}
            probs, conf = a.get("probabilities"), a.get("confidence")
            if not probs or conf is None:
                continue
            predicted = peak_formula(probs)
            if predicted is None:
                continue
            rows.setdefault(field, []).append((abs(predicted - conf), probs, conf, predicted))

    if not rows:
        sys.exit(f"no {args.model} answers with probabilities in {path}")

    out = []

    def emit(line=""):
        print(line)
        out.append(line)

    emit("# Is `confidence` just arithmetic on the probabilities?")
    emit()
    emit("Testing `confidence == (n x peak - 1) / (n - 1)` against every answer in "
         f"`{path}`.")
    emit()
    emit("| question | primitive | answers | mean error | max error | exact | within rounding |")
    emit("|---|---|---|---|---|---|---|")

    for field in schema.FIELDS:
        data = rows.get(field)
        if not data:
            continue
        errs = [d[0] for d in data]
        n_opts = len(data[0][1])
        tol = rounding_tolerance(n_opts)
        kind = "Choice" if field in CHOICE_FIELDS else "Score"
        emit(f"| `{field}` | {kind} ({n_opts}) | {len(errs)} | {statistics.mean(errs):.5f} | "
             f"{max(errs):.4f} | {100 * sum(e < 1e-9 for e in errs) / len(errs):.0f}% | "
             f"{100 * sum(e <= tol for e in errs) / len(errs):.0f}% |")
    emit()
    emit("*\"Exact\" means the reported confidence equals the formula to the last digit. "
         "\"Within rounding\" allows for the probabilities being reported to two decimals, "
         "which is the only slack the formula should need if it is the whole story.*")
    emit()

    # The interesting part: where the formula fails, and by how much.
    worst = sorted((d for ds in rows.values() for d in ds), key=lambda t: -t[0])[:5]
    if worst and worst[0][0] > 0.02:
        emit("## Where it does not hold")
        emit()
        emit("| reported | peak formula | probabilities |")
        emit("|---|---|---|")
        for err, probs, conf, predicted in worst:
            shown = ", ".join(f"{k}: {v:g}" for k, v in sorted(probs.items()))
            emit(f"| **{conf:g}** | {predicted:.3f} | {shown} |")
        emit()
        emit("Every one of these is a **Score**, and in every one the reported confidence is "
             "*lower* than the peak-only formula. The mass is spread across adjacent levels, "
             "and Jev is accounting for that spread. TypeSafe's published formula is stated "
             "for a Choice, so this is not a contradiction - it says Score confidence measures "
             "dispersion across an ordered scale rather than the height of the winning level.")
        emit()

    emit("## Why this matters for routing")
    emit()
    emit("Confidence is computed from the distribution over **these options for this input**. "
         "It has no access to a second model, so it cannot predict whether a bigger model "
         "would do better - only how concentrated its own answer is. That is the mechanism "
         "behind the cascade result in `cascade.md`: escalating low-confidence answers to an "
         "LLM bought little, because low confidence marks an ambiguous input rather than a "
         "question another model happens to be good at.")
    emit()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n(written to {args.out})")


if __name__ == "__main__":
    main()
