#!/usr/bin/env python3
"""
Does a calibrated confidence score tell you when to escalate to a bigger model?

THE QUESTION
------------
The obvious thing to build with a calibrated confidence number is a cascade:
run the cheap model on everything, and when it says it is unsure, pay for the
expensive one. It is the design everybody reaches for, and it sounds free.

This measures it, using only data already collected - both models answered
every message in `results/raw.jsonl`, so every routing policy can be replayed
offline at no cost. Nothing here makes an API call.

WHAT IT MEASURES
----------------
    Jev alone            every answer from Jev
    LLM alone            every answer from the LLM
    Per-message cascade  if any of Jev's four answers is below T, re-ask the
                         whole message
    Per-field cascade    take the LLM's answer only for the specific fields
                         Jev was unsure about
    Oracle               always pick whichever model was right - impossible in
                         production, and the point of computing it is to bound
                         how much any routing policy could ever be worth

Costs use the measured token counts from the run, not the price list, and
assume one LLM call per escalated MESSAGE, because that is what an escalation
actually costs whether one field triggered it or four.

The scoring rules are imported from score_results.py rather than repeated. Two
scorers that drift apart produce two reports that disagree, and the one that
gets quoted is whichever was run last.

Usage:
    python3 tools/cascade_analysis.py
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schema                                        # noqa: E402
from score_results import PRICES, correct, predictions, scoreable   # noqa: E402

THRESHOLDS = (0.50, 0.60, 0.70, 0.80, 0.90, 0.95)


def answered_well(rec, field):
    """One answer, scored by the same argmax rule the main report uses."""
    pred, _, _ = predictions(field, rec)
    return bool(pred is not None and correct(field, rec, pred))


def cost_per_message(records, model):
    rows = [r for r in records if r["model"] == model and r.get("ok")]
    p = PRICES[model]
    tin = statistics.mean(r["usage"].get("input_tokens") or 0 for r in rows)
    tout = statistics.mean(r["usage"].get("output_tokens") or 0 for r in rows)
    return (tin * p["in"] + tout * p["out"]) / 1e6


def warm_median_ms(records, model):
    warm = [r["ms"] for r in records if r["model"] == model and r.get("ok") and not r.get("cold")]
    return statistics.median(warm) if warm else 0.0


def accuracy(pairs, choose):
    """`choose(pair, field)` returns the record whose answer is used."""
    hits = n = 0
    for pair in pairs:
        for field in schema.FIELDS:
            if not scoreable(field, pair["jev"]):
                continue
            n += 1
            hits += answered_well(choose(pair, field), field)
    return (100 * hits / n if n else 0.0), n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default="results/raw.jsonl")
    ap.add_argument("--out", default="results/cascade.md")
    args = ap.parse_args()

    path = Path(args.raw)
    if not path.exists():
        sys.exit(f"{path} not found - run run_benchmark.py first")

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    by_id = {}
    for r in records:
        if r.get("ok"):
            by_id.setdefault(r["id"], {})[r["model"]] = r
    pairs = [g for g in by_id.values() if "jev" in g and "llm" in g]
    if not pairs:
        sys.exit("need successful results for both models - run with --models jev,llm")

    cj, cl = cost_per_message(records, "jev"), cost_per_message(records, "llm")
    mj, ml = warm_median_ms(records, "jev"), warm_median_ms(records, "llm")

    out = []

    def emit(line=""):
        print(line)
        out.append(line)

    emit("# Does confidence tell you when to escalate?")
    emit()
    emit(f"Replayed offline over {len(pairs)} messages that both models answered. "
         "No API calls; every policy below is a different way of reading the same run.")
    emit()

    jev_acc, n_ans = accuracy(pairs, lambda p, f: p["jev"])
    llm_acc, _ = accuracy(pairs, lambda p, f: p["llm"])
    oracle_acc, _ = accuracy(
        pairs, lambda p, f: p["jev"] if answered_well(p["jev"], f) else p["llm"])

    emit(f"Scored over {n_ans} answers (spam rows carry no department, urgency or "
         "frustration and are skipped for those).")
    emit()
    emit("## The four policies")
    emit()
    emit("| policy | accuracy | cost / 1 000 messages | mean latency |")
    emit("|---|---|---|---|")
    emit(f"| Jev alone | **{jev_acc:.1f}%** | **${cj * 1000:.3f}** | {mj:.0f} ms |")
    emit(f"| {schema.LLM_LABEL} alone | {llm_acc:.1f}% | ${cl * 1000:.3f} | {ml:.0f} ms |")

    best_field = {}
    for T in THRESHOLDS:
        hits = n = escalated_msgs = fields_escalated = fields_total = 0
        for pair in pairs:
            touched = False
            for field in schema.FIELDS:
                if not scoreable(field, pair["jev"]):
                    continue
                conf = (pair["jev"]["answers"].get(field) or {}).get("confidence")
                use_llm = conf is not None and conf < T
                fields_total += 1
                fields_escalated += use_llm
                touched = touched or use_llm
                n += 1
                hits += answered_well(pair["llm"] if use_llm else pair["jev"], field)
            escalated_msgs += touched
        share = escalated_msgs / len(pairs)
        best_field[T] = (100 * hits / n, share, 100 * fields_escalated / fields_total,
                         (cj + share * cl) * 1000, mj + share * ml)

    T_best = max(THRESHOLDS, key=lambda t: best_field[t][0])
    acc_b, share_b, fshare_b, cost_b, lat_b = best_field[T_best]
    emit(f"| Confidence-routed cascade (best, T={T_best:.2f}) | {acc_b:.1f}% | "
         f"${cost_b:.3f} | {lat_b:.0f} ms |")
    emit(f"| Oracle — always pick the model that was right | {oracle_acc:.1f}% | "
         f"${(cj + cl) * 1000:.3f} | {mj + ml:.0f} ms |")
    emit()
    emit("*The oracle cannot be built. It is here to bound how much any routing "
         "policy could ever be worth.*")
    emit()

    gain = acc_b - jev_acc
    headroom = oracle_acc - jev_acc
    emit(f"**Escalating on low confidence buys {gain:+.1f} points for "
         f"{cost_b / (cj * 1000):.1f}× the cost of Jev alone.** Perfect routing would be "
         f"worth {headroom:+.1f} points, so confidence-based routing captures "
         f"{100 * gain / headroom:.0f}% of what is actually available.")
    emit()

    emit("## Per-field cascade, across thresholds")
    emit()
    emit("Take the LLM's answer only for the specific fields Jev was unsure about.")
    emit()
    emit("| threshold | fields escalated | messages touching the LLM | accuracy | cost / 1 000 |")
    emit("|---|---|---|---|---|")
    for T in THRESHOLDS:
        acc_t, share, fshare, cost, _ = best_field[T]
        emit(f"| ≥ {T:.2f} | {fshare:.1f}% | {100 * share:.1f}% | "
             f"{acc_t:.1f}% | ${cost:.3f} |")
    emit()

    emit("## Why it does not help: the models are good at different things")
    emit()
    emit("| field | Jev | " + schema.LLM_LABEL + " |")
    emit("|---|---|---|")
    for field in schema.FIELDS:
        rows = [p for p in pairs if scoreable(field, p["jev"])]
        if not rows:
            continue
        j = 100 * sum(answered_well(p["jev"], field) for p in rows) / len(rows)
        l = 100 * sum(answered_well(p["llm"], field) for p in rows) / len(rows)
        mark = lambda v, o: f"**{v:.1f}%**" if v > o else f"{v:.1f}%"  # noqa: E731
        emit(f"| `{field}` | {mark(j, l)} | {mark(l, j)} |")
    emit()
    emit("Jev being unsure does not mean the LLM will be right. Where Jev is weakest "
         "the LLM is better, but where Jev is strongest the LLM is much worse — so "
         "escalating Jev's uncertain answers hands some of them to a model that is "
         "worse at that particular question.")
    emit()
    emit("**Confidence tells you when to ask a human. It does not tell you when to "
         "ask a bigger model.** Those are different questions, and only the first one "
         "is answered by a number that reflects the model's own uncertainty.")
    emit()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n(written to {args.out})")


if __name__ == "__main__":
    main()
