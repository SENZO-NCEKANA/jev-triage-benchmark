#!/usr/bin/env python3
"""
Run every enquiry past Jev and an LLM, recording answers, confidence and timing.

WHY THIS IS A SCRIPT AND NOT A WORKFLOW
---------------------------------------
The headline claim being checked is that Jev is far faster and far cheaper than
an LLM at classification. Measuring that inside an automation tool would fold
the tool's own per-node overhead into every reading, so the published latency
would partly be a measurement of n8n. The instrument has to be thinner than the
thing it measures.

WHAT IS MEASURED, AND WHAT ISN'T
--------------------------------
Latency here is WALL CLOCK from Johannesburg, on a warm keep-alive connection.
It is not inference time. TypeSafe publish 70-500 ms, which is almost certainly
measured at their edge; from here a call costs about 1.1 s, and roughly a third
of that is establishing the connection in the first place. Neither number is
wrong - they measure different things - so this script records both:

  * the first call on a fresh connection is tagged `cold: true`
  * every later call on that connection is tagged `cold: false`

and both models are measured the same way, on the same machine, over the same
connection, in the same run. A like-for-like comparison is the only comparison
worth publishing; putting our measured Jev number next to an LLM's PUBLISHED
number would be dishonest in the other direction.

Results stream to results/raw.jsonl one line at a time, so a failure at row 150
costs one row rather than the whole run. Re-running skips ids already recorded.

Keys come from the environment and are never logged:

    export TYPESAFE_API_KEY=...
    export OPENAI_API_KEY=...

Usage:
    python3 tools/run_benchmark.py --models jev
    python3 tools/run_benchmark.py --models jev,llm
    python3 tools/run_benchmark.py --models jev,llm --limit 20
"""

import argparse
import hashlib
import http.client
import json
import os
import ssl
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schema  # noqa: E402  - the single source of truth for what is asked

JEV_HOST, JEV_PATH = "api.typesafe.ai", "/v1/systemone"
LLM_HOST, LLM_PATH = "api.openai.com", "/v1/chat/completions"
LLM_MODEL = "gpt-4.1-mini"

RETRY_STATUSES = {429, 529, 500, 502, 503, 504}
MAX_ATTEMPTS = 4


class Endpoint:
    """One keep-alive HTTPS connection, reused across calls.

    Reuse is the point: it separates the cost of talking to the service from the
    cost of opening a connection to it, which from South Africa is about a third
    of a single cold call. The first request through a fresh connection is
    reported as cold so the two never get averaged together.
    """

    def __init__(self, host):
        self.host = host
        self.conn = None

    def _connect(self):
        self.conn = http.client.HTTPSConnection(
            self.host, timeout=60, context=ssl.create_default_context()
        )
        return True

    def post(self, path, payload, headers):
        """Returns (status, parsed_body, elapsed_ms, was_cold). Retries on the
        statuses TypeSafe documents as retryable, with exponential backoff."""
        body = json.dumps(payload).encode()
        hdrs = {"Content-Type": "application/json", **headers}

        for attempt in range(1, MAX_ATTEMPTS + 1):
            cold = False
            if self.conn is None:
                cold = self._connect()
            started = time.perf_counter()
            try:
                self.conn.request("POST", path, body=body, headers=hdrs)
                resp = self.conn.getresponse()
                raw = resp.read()
                elapsed_ms = (time.perf_counter() - started) * 1000
                status = resp.status
            except (http.client.HTTPException, OSError) as exc:
                # A keep-alive connection the server has quietly closed looks
                # exactly like this. Drop it and retry on a fresh one.
                self.close()
                if attempt == MAX_ATTEMPTS:
                    return 0, {"error": f"{type(exc).__name__}: {exc}"}, 0.0, True
                time.sleep(2 ** (attempt - 1))
                continue

            if status in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                time.sleep(2 ** (attempt - 1))
                continue

            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"error": "non-JSON response", "text": raw[:400].decode(errors="replace")}
            return status, parsed, elapsed_ms, cold

        return 0, {"error": "exhausted retries"}, 0.0, True

    def close(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None


# ---------------------------------------------------------------------------
# The two arms. Both receive the identical message string and the identical
# criteria wording, straight out of schema.py.
# ---------------------------------------------------------------------------

def call_jev(ep, key, message):
    status, body, ms, cold = ep.post(
        JEV_PATH,
        {"state": message, "model": "jev-latest", "questions": schema.JEV_QUESTIONS},
        {"Authorization": f"Bearer {key}"},
    )
    if status != 200:
        return {"ok": False, "status": status, "error": body, "ms": ms, "cold": cold}

    answers = body.get("answers", {})
    out = {}
    for field in schema.FIELDS:
        a = answers.get(field, {})
        out[field] = {
            # A choice answer is a label; a score answer is a continuous
            # expectation over an ordered scale. Both are kept in their native
            # form and converted only at scoring time, where the rule is stated.
            "answer": a.get("choice") if a.get("type") == "choice" else a.get("score"),
            "confidence": a.get("confidence"),
            "probabilities": a.get("probabilities"),
        }
    return {
        "ok": True,
        "status": status,
        "ms": ms,
        "cold": cold,
        "model_version": body.get("model"),
        "usage": body.get("usage", {}),
        "answers": out,
    }


def call_llm(ep, key, message):
    status, body, ms, cold = ep.post(
        LLM_PATH,
        {
            "model": LLM_MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": schema.LLM_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
        },
        {"Authorization": f"Bearer {key}"},
    )
    if status != 200:
        return {"ok": False, "status": status, "error": body, "ms": ms, "cold": cold}

    try:
        content = json.loads(body["choices"][0]["message"]["content"])
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": status, "error": f"unparseable: {exc}", "ms": ms, "cold": cold}

    out = {}
    for field in schema.FIELDS:
        a = content.get(field) or {}
        if not isinstance(a, dict):        # model returned a bare value
            a = {"answer": a, "confidence": None}
        out[field] = {
            "answer": a.get("answer"),
            "confidence": a.get("confidence"),
            "probabilities": None,          # an LLM does not expose one
        }
    usage = body.get("usage", {})
    return {
        "ok": True,
        "status": status,
        "ms": ms,
        "cold": cold,
        "model_version": body.get("model"),
        "usage": {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
        },
        "answers": out,
    }


# ---------------------------------------------------------------------------

def load_corpus(path):
    raw = Path(path).read_bytes()
    rows = json.loads(raw.decode("utf-8"))
    if not rows:
        sys.exit(f"{path} is empty - run generate_enquiries.py first")
    return rows, hashlib.sha256(raw).hexdigest()[:16]


def already_done(out_path, corpus_sha):
    """(id, model) pairs already recorded, so a re-run resumes instead of
    repeating - and never double-charges for a row.

    Resuming is only safe if the corpus has not changed underneath. It did
    change once: the generator was fixed after the labels were found to
    contradict their own text, and because resume keys on (id, model) alone,
    the next run would have silently kept the superseded rows and scored a mix
    of old and new truth. So every record carries the corpus fingerprint, and a
    mismatch stops the run rather than quietly producing a blended result."""
    done, seen_shas = set(), set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in rec and "model" in rec:
                done.add((rec["id"], rec["model"]))
            seen_shas.add(rec.get("corpus_sha"))

    stale = seen_shas - {corpus_sha}
    if stale:
        sys.exit(
            f"\n{out_path} holds results for a different corpus "
            f"({', '.join(str(s) for s in sorted(stale))} vs {corpus_sha}).\n"
            f"The labels have moved, so those rows can no longer be scored "
            f"alongside new ones.\nMove the old file aside and re-run:\n"
            f"    mv {out_path} {out_path.with_suffix('.superseded.jsonl')}\n"
        )
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default="sample-data/enquiries.json")
    ap.add_argument("--out", default="results/raw.jsonl")
    ap.add_argument("--models", default="jev", help="comma separated: jev,llm")
    ap.add_argument("--limit", type=int, help="only the first N enquiries")
    args = ap.parse_args()

    wanted = [m.strip() for m in args.models.split(",") if m.strip()]
    for m in wanted:
        if m not in ("jev", "llm"):
            sys.exit(f"unknown model '{m}' - use jev and/or llm")

    keys = {}
    if "jev" in wanted:
        keys["jev"] = os.environ.get("TYPESAFE_API_KEY")
        if not keys["jev"]:
            sys.exit("TYPESAFE_API_KEY is not set")
    if "llm" in wanted:
        keys["llm"] = os.environ.get("OPENAI_API_KEY")
        if not keys["llm"]:
            sys.exit("OPENAI_API_KEY is not set")

    rows, corpus_sha = load_corpus(args.corpus)
    if args.limit:
        rows = rows[: args.limit]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = already_done(out_path, corpus_sha)
    print(f"corpus {args.corpus}  fingerprint {corpus_sha}  {len(rows)} enquiries")

    endpoints = {}
    if "jev" in wanted:
        endpoints["jev"] = (Endpoint(JEV_HOST), call_jev)
    if "llm" in wanted:
        endpoints["llm"] = (Endpoint(LLM_HOST), call_llm)

    started = time.time()
    counts = {m: {"ok": 0, "fail": 0, "skip": 0} for m in wanted}

    with out_path.open("a", encoding="utf-8") as fh:
        for i, row in enumerate(rows, 1):
            for model in wanted:
                if (row["id"], model) in done:
                    counts[model]["skip"] += 1
                    continue

                ep, fn = endpoints[model]
                result = fn(ep, keys[model], row["message"])

                # The truth travels with the prediction, so raw.jsonl can be
                # scored by anyone without also needing the corpus in hand.
                record = {
                    "id": row["id"],
                    "model": model,
                    "corpus_sha": corpus_sha,
                    "channel": row["channel"],
                    "is_ambiguous": row["is_ambiguous"],
                    "truth": {
                        "department": row["true_department"],
                        "alt_department": row["alt_department"],
                        "urgency": row["true_urgency"],
                        "frustration": row["true_frustration"],
                        "is_spam": row["true_is_spam"],
                    },
                    **result,
                }
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                fh.flush()

                counts[model]["ok" if result.get("ok") else "fail"] += 1
                if not result.get("ok"):
                    print(f"  ! {row['id']} {model} -> {result.get('status')} "
                          f"{str(result.get('error'))[:120]}")

            if i % 10 == 0 or i == len(rows):
                rate = i / max(time.time() - started, 0.001)
                print(f"  {i}/{len(rows)} enquiries   {rate:.2f}/s")

    for ep, _ in endpoints.values():
        ep.close()

    print(f"\nwrote {out_path}  ({time.time() - started:.1f}s)")
    for model in wanted:
        c = counts[model]
        print(f"  {model:4}  ok {c['ok']}   failed {c['fail']}   already done {c['skip']}")
    print("\nNext: python3 tools/score_results.py")


if __name__ == "__main__":
    main()
