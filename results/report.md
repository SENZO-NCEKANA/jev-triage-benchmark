# Jev triage benchmark — results

- Corpus fingerprint: `bc7bf105e2be42d4`
- Records scored: **400**
- `jev`: 200 calls, model version jev-1.13.0
- `llm`: 200 calls, model version gpt-4.1-mini-2025-04-14

Ambiguous rows accept either `department` or `alt_department` as correct.

## Accuracy against known labels

| field | rule | jev | llm |
|---|---|---|---|
| `department` | exact |  99.5% (186/187) |  99.5% (186/187) |
| `urgency` | argmax |  85.0% (159/187) |  87.2% (163/187) |
| `urgency` | round |  86.1% (161/187) |  87.2% (163/187) |
| `urgency` | MAE | 0.19 | 0.13 |
| `is_spam` | exact | 100.0% (200/200) |  99.0% (198/200) |
| `frustration` | argmax |  86.6% (162/187) |  73.3% (137/187) |
| `frustration` | round |  86.6% (162/187) |  73.3% (137/187) |
| `frustration` | MAE | 0.16 | 0.27 |

*MAE is mean absolute error against the true level, lower is better; it is the only row that uses the full precision of a score answer.*

## Calibration — does a stated confidence mean anything?

Every answer, pooled across all four fields, bucketed by the confidence the model reported. A calibrated model's accuracy tracks its confidence down the column.

### `jev`

| confidence | answers | accuracy | gap |
|---|---|---|---|
| 0.00–0.50 | 46 |  63.0% | +0.31 |
| 0.50–0.60 | 21 |  71.4% | +0.18 |
| 0.60–0.70 | 16 |  87.5% | +0.23 |
| 0.70–0.80 | 37 |  83.8% | +0.10 |
| 0.80–0.90 | 63 |  96.8% | +0.11 |
| 0.90–1.00 | 346 |  94.5% | -0.01 |
| 1.00 | 232 |  99.1% | -0.01 |

**Expected calibration error: 0.048** — the average distance between stated confidence and actual accuracy, weighted by how many answers fall in each bucket. Lower is better.

### `llm`

| confidence | answers | accuracy | gap |
|---|---|---|---|
| 0.60–0.70 | 6 |   0.0% | -0.60 |
| 0.70–0.80 | 75 |  56.0% | -0.14 |
| 0.80–0.90 | 159 |  81.1% | +0.01 |
| 0.90–1.00 | 339 |  97.6% | +0.07 |
| 1.00 | 182 | 100.0% | +0.00 |

**Expected calibration error: 0.050** — the average distance between stated confidence and actual accuracy, weighted by how many answers fall in each bucket. Lower is better.

## Does confidence drop where the answer is genuinely unclear?

The corpus contains rows written to be routable two ways. If the confidence number is doing real work, it should be visibly lower on those.

| model | clean rows | ambiguous rows | difference |
|---|---|---|---|
| `jev` | 0.975 | 0.580 | **-0.395** |
| `llm` | 0.906 | 0.861 | **-0.046** |

*Mean reported confidence on `department`. A negative difference is the behaviour you want — and is what makes a routing threshold possible.*

## What each confidence threshold buys

Auto-file every answer at or above the threshold, send the rest to a person. This is the table a routing threshold should be read off, rather than picking a round number because it sounds right.

| threshold | jev auto-files | at accuracy | llm auto-files | at accuracy |
|---|---|---|---|---|
| ≥ 0.70 |  89.1% | ** 95.7%** |  99.2% | ** 90.6%** |
| ≥ 0.80 |  84.2% | ** 96.4%** |  89.4% | ** 94.4%** |
| ≥ 0.90 |  76.0% | ** 96.4%** |  68.5% | ** 98.5%** |
| ≥ 0.95 |  56.8% | ** 96.3%** |  31.3% | ** 99.2%** |

## How much of the confidence scale each model uses

| model | distinct values | answers | most common |
|---|---|---|---|
| `jev` | **69** | 800 | `1` used 249× |
| `llm` | **11** | 800 | `0.9` used 299× |

*A confidence number you can threshold on has to vary. One that clusters on a few round values cannot separate a sure answer from an unsure one.*

## Where department routing goes wrong

### `jev`

| true ↓ / predicted → | billing | technical | sales |
|---|---|---|---|
| **billing** | 63 | 1 | 0 |
| **technical** | 6 | 70 | 0 |
| **sales** | 1 | 0 | 46 |

### `llm`

| true ↓ / predicted → | billing | technical | sales |
|---|---|---|---|
| **billing** | 62 | 2 | 0 |
| **technical** | 8 | 68 | 0 |
| **sales** | 1 | 0 | 46 |

*Counted against `true_department` only, so an ambiguous row answered with its `alt_department` appears off the diagonal here while still counting as correct in the accuracy table. The matrix is for seeing which pairs get confused, not for re-deriving the score.*

## Latency and cost, measured here

Wall clock from Johannesburg, both models in the same run, over the same connection. **Not** inference time, and not comparable to any published figure.

| model | cold call | warm median | warm p95 | in tokens (mean) | cost / 1 000 classifications |
|---|---|---|---|---|---|
| `jev` | 1095 ms | 415 ms | 1356 ms | 624 | **$0.026** |
| `llm` | 3049 ms | 1496 ms | 3075 ms | 479 | **$0.308** |

*Prices used: Jev $0.042/M input, output free; gpt-4.1-mini $0.4/M input and $1.6/M output.*

## Where the two models disagree on department

| id | ambiguous | true | jev | llm | who was right |
|---|---|---|---|---|---|
| ENQ-0058 | yes | technical | technical (0.27) | billing (0.90) | jev, llm |
| ENQ-0061 | yes | billing | billing (0.87) | technical (0.80) | jev, llm |
| ENQ-0127 | yes | technical | technical (0.33) | billing (0.80) | jev, llm |

*3 disagreements. Confidence in brackets.*

