# What a calibrated confidence score is actually good for

An independent measurement of [TypeSafe AI's](https://typesafe.ai) **Jev** against **GPT-4.1-mini**, over 200 South African customer enquiries that carry **known correct answers**.

Jev shipped on 15 September 2026. It returns a probability distribution and a confidence score with every answer, and the interesting question isn't whether those numbers exist — it's what you can safely build on them.

**The finding:**

> **Confidence tells you when to ask a human. It does not tell you when to ask a bigger model.**

Those sound like the same question. They are not, and the difference is worth about 7× in running costs.

Every number here is measured from Johannesburg and recomputable from [`results/raw.jsonl`](results/raw.jsonl).

---

## Two routing questions, two very different answers

### 1. "Should a person look at this?" — yes, confidence answers this well

![What each confidence threshold buys](docs/charts/threshold-tradeoff.png)

Set a threshold, auto-file everything above it, send the rest to a human:

| threshold | Jev auto-files | at accuracy | GPT auto-files | at accuracy |
|---|---|---|---|---|
| ≥ 0.70 | **82.9%** | **94.6%** | 99.3% | 86.5% |
| ≥ 0.80 | 77.7% | 94.9% | 89.4% | 90.1% |
| ≥ 0.90 | 69.1% | 96.6% | 68.5% | 96.7% |
| ≥ 0.95 | 50.6% | 97.9% | 34.6% | 99.2% |

**At a matched ~95% accuracy bar, Jev automates 83% of decisions and GPT automates 68%.** Not because Jev is more accurate — the gap is 1.9 points overall — but because GPT's confidence is compressed into the top of the scale, so a threshold at 0.70 lets 99.3% through and filters nothing. That is not a dial; it is an on switch.

### 2. "Should a bigger model look at this?" — no, confidence does not answer this

The obvious thing to build is a cascade: run the cheap model on everything, escalate what it's unsure about. Replayed offline over the same run ([full working](results/cascade.md)):

| policy | accuracy | cost / 1 000 |
|---|---|---|
| **Jev alone** | **88.0%** | **$0.024** |
| GPT-4.1-mini alone | 86.1% | $0.291 |
| Confidence-routed cascade (best, T = 0.70) | 89.2% | $0.180 |
| *Oracle — always pick the model that was right* | *92.0%* | *$0.315* |

**Escalating on low confidence buys +1.2 points for 7.4× the cost.** Perfect routing would be worth +3.9 points, so confidence captures under a third of what is actually on the table.

The reason is visible per-question:

![Accuracy by question, cost, and latency](docs/charts/headline.png)

Jev being unsure doesn't mean the other model will be right. Where Jev is weakest — `urgency` — GPT is better. But where Jev is strongest — `frustration`, by 19 points — GPT is much worse. Escalating Jev's uncertain answers hands a share of them to a model that is worse at that particular question.

**This is consistent with TypeSafe's own documentation**, which states that choice and score confidence *"summarizes distribution concentration, not overall workflow correctness."* It measures how concentrated the probability mass is for **this input against these options**. It was never a claim about how a different model would do. The benchmark reproduces that behaviour from the outside.

---

## Why the number is worth having

![Does the confidence number mean anything?](docs/charts/confidence-spread.png)

Across 800 answers, **Jev used 78 distinct confidence values. GPT-4.1-mini used 11** — and `0.9` alone accounted for 276 of them.

GPT was *told* not to do this. Its system prompt says, verbatim:

> Use the full range. If a message could reasonably be routed two ways, say so with a lower confidence rather than picking one at high confidence.

It didn't. On the 23 messages written to be genuinely routable two ways:

| | clean messages | genuinely ambiguous | drop |
|---|---|---|---|
| **Jev** | 0.977 | 0.586 | **−0.390** |
| GPT-4.1-mini | 0.912 | 0.870 | −0.043 |

**Nine times the drop.** One model's confidence is a property of the prediction; the other's is a sentence it chose to write. Asking politely does not convert the second into the first.

![Reliability diagram](docs/charts/reliability.png)

Expected calibration error: **Jev 0.042, GPT 0.061**. But the direction matters more than the magnitude — Jev errs toward *under*-confidence at the low end, GPT sits *below* the line through 0.6–0.85. Those are not symmetric: under-confidence costs you automation you could have had, over-confidence costs you correctness you didn't know you'd lost.

---

## Where Jev loses

**Urgency: 64.7% against GPT's 76.5%, and the errors run one way — 60 over-reads against 6 under-reads.**

Part of this is my scale. The bottom two levels — *"Not urgent"* and *"Needs attention this week"* — sit close together, and **both** models push messages up into the second: 37 messages were called more urgent than the label by Jev and GPT alike, which says the boundary is soft.

But 23 more were over-read by Jev while GPT matched the label exactly, and those aren't a scale problem:

> Good afternoon, **Sorry to bother you.** My invoice INV-2026-2535 says R687 but I am on the Enterprise plan which was quoted at a different price. Please explain the difference. **Whenever you get a chance. Thank you kindly.**

Maximally polite, explicitly deadline-free, and Jev rates it *needs attention this week*. **If you route on urgency, calibrate against your own labelled sample first.**

The mirror image is `frustration`, where Jev leads by 19 points at roughly half the mean error. Tone it reads well; deadlines it does not.

---

## Speed and cost

| | cold call | warm median | warm p95 | mean input tokens | cost / 1 000 |
|---|---|---|---|---|---|
| Jev | 1 177 ms | **417 ms** | 768 ms | 578 | **$0.024** |
| GPT-4.1-mini | 9 679 ms | 1 512 ms | 4 394 ms | 436 | $0.291 |

**3.6× faster and 12× cheaper**, measured. TypeSafe's published figures are 40–200× and ~400×; those are presumably drawn against frontier models, and GPT-4.1-mini is already small and cheap, which makes this the *hardest* comparison available. Jev wins it on both axes anyway — and note it sends **more** input tokens (578 vs 436), because each question carries its own criteria, and is still 12× cheaper.

**Connection setup is most of a single call and is paid once.** A cold call from South Africa costs ~1.2 s; every call after it on the same connection costs ~0.4 s. An earlier version of this benchmark opened a fresh connection per message and reported 1.1 s as Jev's latency — it was measuring TLS handshakes.

⚠️ Wall clock from one location on consumer fibre. Not inference time, and not comparable to anyone's published latency, including TypeSafe's 70–500 ms, which is a different measurement taken elsewhere.

---

## What I'd build with this

A triage desk for a small business, where **the escalation target is a person, not a bigger model**:

```
inbound message
      ↓
   Jev — four questions, one call, ~0.4 s, $0.000024
      ↓
confidence ≥ 0.70  →  auto-file to the right queue      (83% of traffic, 94.6% correct)
confidence <  0.70  →  a human, with the distribution shown
```

Built in n8n. Same workflow, same threshold, same model — two messages, two destinations:

**A clean billing query.** Jev answers `billing` at 1.00 confidence, and it files itself:

![Routed automatically](docs/screenshots/ENQ-0006.png)

**A message that is honestly two things at once** — the account is locked *and* the payment went through. Jev answers `technical` at **0.27**, its least certain department call of all 200, and a person gets it:

![Routed to a human](docs/screenshots/ENQ-0058.png)

The model doesn't refuse, and it doesn't hedge in prose. It gives an answer *and* a number saying don't act on this one — and the threshold does the rest. GPT-4.1-mini answered the same class of message at 0.80–0.90 every time, which is why this branch would never have fired.

At $0.024 per thousand classifications, the economics work at South African price points where an LLM-per-message pipeline doesn't. The threshold is **0.70 because the table above says so** — going to 0.80 costs 5 points of automation to buy 0.3 points of accuracy, and going to 0.90 costs 14 points to buy 2. Pick it from your own measurements; the number here is right for this corpus and this tolerance for a misroute, which in a support inbox costs someone a forward.

TypeSafe's own guidance says the same thing more bluntly: treat *"cookbook thresholds and demo results as examples to evaluate, not universal rules."* This repository is that evaluation, for one domain.

---

## How the corpus works

Running two models over the same messages tells you how often they agree. **Agreement is not accuracy** — two models can agree and both be wrong, and a confidently wrong model is indistinguishable from a confidently right one unless you already know the answer.

So every message is generated **from** its label rather than labelled afterwards. A template fixes the department, a tone wrapper fixes the frustration level, an urgency clause fixes the urgency. The label is the recipe, not a judgement made later by someone reading the text.

| | |
|---|---|
| Messages | 200, seed 42, fully reproducible |
| Labels | `department` · `urgency` 0–2 · `frustration` 0–2 · `is_spam` |
| Ambiguous | 23, each carrying a second acceptable department |
| Spam | 13, carrying **blank** urgency and frustration |
| Channels | email, web form, WhatsApp — identical labels across registers |
| Setting | ZAR, 15% VAT, local banks and gateways, load-shedding; every name, company and reference fictional |

**Blank is not zero.** Spam has no honest department and no honest urgency — scam mail demanding *"immediate payment"* isn't calmly unurgent, it's something the question was never meaningfully asked about. Those rows are scored on `is_spam` and skipped elsewhere.

Both models get **identical** wording. The criteria live once in [`tools/schema.py`](tools/schema.py) and are imported by the generator, the benchmark and both scorers. Defining them twice is how a benchmark quietly stops comparing like with like.

**Scoring a continuous answer.** Jev answers an ordered question with a continuous expectation (`0.7`), not a discrete label. Converting one to the other is a judgement, so all three readings are reported every time: **argmax** of the distribution, the **rounded** score, and **mean absolute error**. See [`results/report.md`](results/report.md).

---

## What went wrong three times

The labels were wrong, not the model — three separate times.

| | |
|---|---|
| **1** | WhatsApp messages truncated at a word count, cutting *"My invoice says R687 but"* mid-sentence and removing the signal the row was labelled for. |
| **2** | Frustration wording asserted the sender had been waiting — *"Four emails. FOUR. And not one reply."* — on messages labelled *not urgent*. 15 rows contradicted themselves. |
| **3** | Closers set same-day deadlines on messages labelled *needs attention this week*, and spam rows carried an invented urgency of 0 their text flatly contradicted. |

Each was found by a model getting an answer "wrong" and the disagreement turning out to be correct. The tell was identical every time:

> **When two independent models agree against your ground truth, suspect your ground truth.**

Separating the 37 rows where *both* models overshot from the 23 where only Jev did is what turned "Jev is bad at urgency" into the more accurate and more useful "Jev over-reads urgency, **and** my bottom two levels are too close together."

---

## Reproduce it

Python 3.9+. Standard library only, except `matplotlib` to redraw the charts.

```bash
export TYPESAFE_API_KEY=...
export OPENAI_API_KEY=...

python3 tools/generate_enquiries.py           # 200 labelled enquiries, seed 42
python3 tools/run_benchmark.py --models jev,llm
python3 tools/score_results.py                # -> results/report.md
python3 tools/cascade_analysis.py             # -> results/cascade.md
python3 tools/make_charts.py                  # -> docs/charts/
```

About 8 minutes and roughly 9 US cents, almost all of it the LLM arm.

| | |
|---|---|
| [`tools/schema.py`](tools/schema.py) | the four questions and their criteria, defined once |
| [`tools/generate_enquiries.py`](tools/generate_enquiries.py) | builds the corpus from its labels |
| [`tools/run_benchmark.py`](tools/run_benchmark.py) | both arms, keep-alive connections, cold/warm tagging |
| [`tools/score_results.py`](tools/score_results.py) | accuracy, calibration, confusion, cost, latency |
| [`tools/cascade_analysis.py`](tools/cascade_analysis.py) | routing policies replayed offline |
| [`results/raw.jsonl`](results/raw.jsonl) | every answer, confidence, distribution and timing |

**The workflow.** Import [`workflows/jev-triage-benchmark.json`](workflows/jev-triage-benchmark.json) into n8n, then create a **Header Auth** credential named `Jev v2` with name `Authorization` and value `Bearer <your key>`. It ships with a sample message loaded, so it runs on import.

[`tools/sanitise_workflow.py`](tools/sanitise_workflow.py) is what produced that file — it strips the instance fingerprint, the workflow and node ids, tags, and the credential's internal id, and empties `pinData`. That last one matters most: pinned nodes store their captured output verbatim, so on a workflow that has touched real mail, `pinData` *is* the mail.

A sanitiser only removes what it was written to remove, though, which is why the rule it can't enforce is the one that counts: **read the exported file in full before committing it.** Doing that here caught `05b · Human review` shipping with no fields set — a node that ran green, passed an item through, and did nothing.

Results stream to disk one line at a time and re-runs resume, so a failure at row 150 costs one row. Every record carries a fingerprint of the corpus it was scored against and the run **aborts** rather than blending two corpora — added after exactly that nearly happened.

---

## Limits

- **One model pair, one domain, one language.** Small-business support email in South African English.
- **200 messages** separates a −0.390 confidence drop from a −0.043 one comfortably. It does not separate 99.5% from 100.0% on department; treat that as a tie.
- **Synthetic messages** are cleaner than real inbound mail, so these accuracy figures are an upper bound for both models.
- **`is_spam` was modelled as a two-option choice.** TypeSafe documents a third primitive — **Noul** — for yes/no conditions, which would be the correct shape for that question and was not tested here.
- **Urgency labels remain the weakest part**, by this project's own evidence. Lean on the frustration, department and spam results.
- One location, one afternoon, a model a fortnight old.

---

## Licence

MIT — see [LICENSE](LICENSE).
