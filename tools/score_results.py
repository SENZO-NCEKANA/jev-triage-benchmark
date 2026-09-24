#!/usr/bin/env python3
"""
Score results/raw.jsonl against the known labels.

WHAT THIS DOES THAT AN AGREEMENT TEST DOESN'T
---------------------------------------------
Every row carries the label it was generated from, so this measures whether
each model is RIGHT - not merely whether the two models say the same thing.
Two models can agree and both be wrong, and that failure is invisible to any
comparison that only puts them side by side.

THE DECISION RULE IS STATED, NOT CHOSEN LATE
--------------------------------------------
Jev answers a `score` question with a continuous expectation over an ordered
scale (0.7), which is not the same object as a discrete label. Turning it into
one is a judgement call, and picking whichever rule flatters the result is how
benchmarks stop being worth reading. So all three are reported every time:

    argmax   the most likely level in the returned distribution
    round    the score rounded to the nearest level
    MAE      mean absolute error against the true level, which is the only
             measure that uses the full precision of the answer

For `department`, the 33-odd deliberately ambiguous rows carry a second
acceptable answer, and either counts as correct. That allowance is printed in
the report rather than buried here.

CALIBRATION IS THE POINT
------------------------
Accuracy says how often a model is right. Calibration says whether its stated
confidence means anything - whether the answers it gave 0.9 to are right about
90% of the time. A model that is accurate but uncalibrated cannot be used with
a routing threshold, which is the entire practical claim being tested.

Usage:
    python3 tools/score_results.py
    python3 tools/score_results.py --out results/report.md
"""

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schema  # noqa: E402

CHOICE_FIELDS = ("department", "is_spam")
SCORE_FIELDS = ("urgency", "frustration")

# Published prices, recorded with the date they were taken so the figures below
# can be recomputed when they change. Output tokens are free on Jev.
PRICES = {
    "jev": {"in": 0.042, "out": 0.0},      # TypeSafe, USD per 1M tokens, 22 Sep 2026
    "llm": {"in": 0.40, "out": 1.60},      # gpt-4.1-mini, USD per 1M tokens, 22 Sep 2026
}

CONF_BUCKETS = [(0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8),
                (0.8, 0.9), (0.9, 1.0), (1.0, 1.01)]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def predictions(field, rec):
    """Every way of reading one answer, as (argmax, rounded, abs_error).

    A choice answer has only one reading, so argmax is the answer and the other
    two are None. A score answer has three, and all three are reported."""
    a = rec["answers"].get(field) or {}
    ans, truth = a.get("answer"), rec["truth"][field]

    if field in CHOICE_FIELDS:
        return ans, None, None

    score = num(ans)
    if score is None:
        return None, None, None

    probs = a.get("probabilities")
    if probs:
        argmax = int(max(probs, key=lambda k: probs[k]))
    else:
        argmax = int(round(score))       # an LLM returns a level, not a distribution
    return argmax, int(round(score)), abs(score - float(truth))


def correct(field, rec, pred):
    truth = rec["truth"]
    if field == "department":
        # Either reading of a deliberately ambiguous message counts.
        return pred == truth["department"] or (
            bool(truth["alt_department"]) and pred == truth["alt_department"]
        )
    if field == "is_spam":
        return pred == truth["is_spam"]
    return pred is not None and int(pred) == int(truth[field])


def scoreable(field, rec):
    """Spam rows carry no honest department, urgency or frustration, so they are
    excluded from those three rather than counted against a model. A blank in
    the corpus means "no ground truth exists", which is not the same as zero -
    scam mail demanding "immediate payment" is not calmly unurgent, it is
    something the question was never meaningfully asked about. Spam rows are
    still fully scored on `is_spam`, which is the question that does apply."""
    truth = rec["truth"].get(field)
    if field == "department" or field in SCORE_FIELDS:
        return truth != "" and truth is not None
    return True


def pct(n, d):
    return f"{100 * n / d:5.1f}%" if d else "    -"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default="results/raw.jsonl")
    ap.add_argument("--out", default="results/report.md")
    args = ap.parse_args()

    path = Path(args.raw)
    if not path.exists():
        sys.exit(f"{path} not found - run run_benchmark.py first")

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    ok = [r for r in records if r.get("ok")]
    failed = [r for r in records if not r.get("ok")]
    if not ok:
        sys.exit("no successful records to score")

    models = sorted({r["model"] for r in ok})
    shas = {r.get("corpus_sha") for r in ok}
    out = []

    def emit(line=""):
        print(line)
        out.append(line)

    emit("# Jev triage benchmark — results")
    emit()
    emit(f"- Corpus fingerprint: `{', '.join(str(s) for s in shas)}`")
    emit(f"- Records scored: **{len(ok)}**" + (f" ({len(failed)} failed calls)" if failed else ""))
    for m in models:
        rows = [r for r in ok if r["model"] == m]
        vers = sorted({r.get("model_version") for r in rows if r.get("model_version")})
        emit(f"- `{m}`: {len(rows)} calls, model version {', '.join(vers) or 'n/a'}")
    emit()
    emit("Ambiguous rows accept either `department` or `alt_department` as correct.")
    emit()

    # ---------------- accuracy -------------------------------------------
    emit("## Accuracy against known labels")
    emit()
    emit("| field | rule | " + " | ".join(models) + " |")
    emit("|---|---|" + "---|" * len(models))

    for field in schema.FIELDS:
        rules = ["exact"] if field in CHOICE_FIELDS else ["argmax", "round", "MAE"]
        for rule in rules:
            cells = []
            for m in models:
                rows = [r for r in ok if r["model"] == m and scoreable(field, r)]
                if rule == "MAE":
                    errs = [p[2] for p in (predictions(field, r) for r in rows) if p[2] is not None]
                    cells.append(f"{statistics.mean(errs):.2f}" if errs else "-")
                else:
                    hits = n = 0
                    for r in rows:
                        argmax, rounded, _ = predictions(field, r)
                        pred = argmax if rule in ("exact", "argmax") else rounded
                        if pred is None:
                            continue
                        n += 1
                        hits += correct(field, r, pred)
                    cells.append(f"{pct(hits, n)} ({hits}/{n})")
            emit(f"| `{field}` | {rule} | " + " | ".join(cells) + " |")
    emit()
    emit("*MAE is mean absolute error against the true level, lower is better; "
         "it is the only row that uses the full precision of a score answer.*")
    emit()

    # ---------------- calibration ----------------------------------------
    emit("## Calibration — does a stated confidence mean anything?")
    emit()
    emit("Every answer, pooled across all four fields, bucketed by the confidence "
         "the model reported. A calibrated model's accuracy tracks its confidence "
         "down the column.")
    emit()

    for m in models:
        emit(f"### `{m}`")
        emit()
        emit("| confidence | answers | accuracy | gap |")
        emit("|---|---|---|---|")
        ece = total = 0
        for lo, hi in CONF_BUCKETS:
            hits = n = 0
            conf_sum = 0.0
            for r in (x for x in ok if x["model"] == m):
                for field in schema.FIELDS:
                    if not scoreable(field, r):
                        continue
                    c = num((r["answers"].get(field) or {}).get("confidence"))
                    if c is None or not (lo <= c < hi):
                        continue
                    argmax, _, _ = predictions(field, r)
                    if argmax is None:
                        continue
                    n += 1
                    conf_sum += c
                    hits += correct(field, r, argmax)
            if not n:
                continue
            acc, mean_conf = hits / n, conf_sum / n
            gap = acc - mean_conf
            label = "1.00" if lo >= 1.0 else f"{lo:.2f}–{hi:.2f}"
            emit(f"| {label} | {n} | {pct(hits, n)} | {gap:+.2f} |")
            ece += n * abs(gap)
            total += n
        emit()
        if total:
            emit(f"**Expected calibration error: {ece / total:.3f}** "
                 f"— the average distance between stated confidence and actual accuracy, "
                 f"weighted by how many answers fall in each bucket. Lower is better.")
        emit()

    # ---------------- ambiguity ------------------------------------------
    emit("## Does confidence drop where the answer is genuinely unclear?")
    emit()
    emit("The corpus contains rows written to be routable two ways. If the confidence "
         "number is doing real work, it should be visibly lower on those.")
    emit()
    emit("| model | clean rows | ambiguous rows | difference |")
    emit("|---|---|---|---|")
    for m in models:
        vals = {}
        for flag in ("no", "yes"):
            cs = [num((r["answers"].get("department") or {}).get("confidence"))
                  for r in ok if r["model"] == m and r["is_ambiguous"] == flag
                  and scoreable("department", r)]
            cs = [c for c in cs if c is not None]
            vals[flag] = statistics.mean(cs) if cs else None
        if vals["no"] is None or vals["yes"] is None:
            continue
        emit(f"| `{m}` | {vals['no']:.3f} | {vals['yes']:.3f} | "
             f"**{vals['yes'] - vals['no']:+.3f}** |")
    emit()
    emit("*Mean reported confidence on `department`. A negative difference is the "
         "behaviour you want — and is what makes a routing threshold possible.*")
    emit()

    # ---------------- confusion ------------------------------------------
    emit("## Where department routing goes wrong")
    emit()
    for m in models:
        cm = defaultdict(Counter)
        for r in (x for x in ok if x["model"] == m and scoreable("department", x)):
            pred, _, _ = predictions("department", r)
            cm[r["truth"]["department"]][pred] += 1
        labels = list(schema.DEPARTMENTS)
        emit(f"### `{m}`")
        emit()
        emit("| true ↓ / predicted → | " + " | ".join(labels) + " |")
        emit("|---|" + "---|" * len(labels))
        for t in labels:
            emit(f"| **{t}** | " + " | ".join(str(cm[t][p]) for p in labels) + " |")
        emit()
    emit("*Counted against `true_department` only, so an ambiguous row answered with its "
         "`alt_department` appears off the diagonal here while still counting as correct "
         "in the accuracy table. The matrix is for seeing which pairs get confused, not "
         "for re-deriving the score.*")
    emit()

    # ---------------- latency & cost -------------------------------------
    emit("## Latency and cost, measured here")
    emit()
    emit("Wall clock from Johannesburg, both models in the same run, over the same "
         "connection. **Not** inference time, and not comparable to any published figure.")
    emit()
    emit("| model | cold call | warm median | warm p95 | in tokens (mean) | "
         "cost / 1 000 classifications |")
    emit("|---|---|---|---|---|---|")
    for m in models:
        rows = [r for r in ok if r["model"] == m]
        cold = [r["ms"] for r in rows if r.get("cold")]
        warm = sorted(r["ms"] for r in rows if not r.get("cold"))
        tin = [r["usage"].get("input_tokens") or 0 for r in rows]
        tout = [r["usage"].get("output_tokens") or 0 for r in rows]
        p = PRICES.get(m, {"in": 0, "out": 0})
        cost = (statistics.mean(tin) * p["in"] + statistics.mean(tout) * p["out"]) / 1e6 * 1000
        p95 = warm[int(len(warm) * 0.95)] if len(warm) > 1 else (warm[0] if warm else 0)
        emit(f"| `{m}` | {statistics.mean(cold):.0f} ms | "
             f"{statistics.median(warm):.0f} ms | {p95:.0f} ms | "
             f"{statistics.mean(tin):.0f} | **${cost:.3f}** |")
    emit()
    emit(f"*Prices used: Jev ${PRICES['jev']['in']}/M input, output free; "
         f"gpt-4.1-mini ${PRICES['llm']['in']}/M input and ${PRICES['llm']['out']}/M output.*")
    emit()

    # ---------------- disagreements --------------------------------------
    if len(models) > 1:
        emit("## Where the two models disagree on department")
        emit()
        by_id = defaultdict(dict)
        for r in ok:
            by_id[r["id"]][r["model"]] = r
        emit("| id | ambiguous | true | " + " | ".join(models) + " | who was right |")
        emit("|---|---|---|" + "---|" * (len(models) + 1))
        shown = 0
        for rid in sorted(by_id):
            got = by_id[rid]
            if len(got) < len(models) or not scoreable("department", next(iter(got.values()))):
                continue
            preds = {m: predictions("department", got[m])[0] for m in models}
            if len(set(preds.values())) == 1:
                continue
            rec = next(iter(got.values()))
            right = [m for m in models if correct("department", got[m], preds[m])] or ["neither"]
            cells = " | ".join(
                f"{preds[m]} ({num((got[m]['answers']['department'] or {}).get('confidence')):.2f})"
                for m in models)
            emit(f"| {rid} | {rec['is_ambiguous']} | {rec['truth']['department']} | "
                 f"{cells} | {', '.join(right)} |")
            shown += 1
        emit()
        emit(f"*{shown} disagreements. Confidence in brackets.*")
        emit()

    if failed:
        emit("## Failed calls")
        emit()
        for r in failed[:20]:
            emit(f"- `{r['id']}` {r['model']} → {r.get('status')} {str(r.get('error'))[:120]}")
        emit()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n(written to {args.out})")


if __name__ == "__main__":
    main()
