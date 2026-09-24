# Jev triage benchmark — results

- Corpus fingerprint: `4603f747238e03b8`
- Records scored: **400**
- `jev`: 200 calls, model version jev-1.13.0
- `llm`: 200 calls, model version gpt-4.1-mini-2025-04-14

Ambiguous rows accept either `department` or `alt_department` as correct.

## Accuracy against known labels

| field | rule | jev | llm |
|---|---|---|---|
| `department` | exact |  99.5% (186/187) | 100.0% (187/187) |
| `urgency` | argmax |  64.7% (121/187) |  76.5% (143/187) |
| `urgency` | round |  65.2% (122/187) |  76.5% (143/187) |
| `urgency` | MAE | 0.41 | 0.24 |
| `is_spam` | exact | 100.0% (200/200) |  99.0% (198/200) |
| `frustration` | argmax |  87.2% (163/187) |  67.9% (127/187) |
| `frustration` | round |  87.2% (163/187) |  67.9% (127/187) |
| `frustration` | MAE | 0.16 | 0.32 |

*MAE is mean absolute error against the true level, lower is better; it is the only row that uses the full precision of a score answer.*

## Calibration — does a stated confidence mean anything?

Every answer, pooled across all four fields, bucketed by the confidence the model reported. A calibrated model's accuracy tracks its confidence down the column.

### `jev`

| confidence | answers | accuracy | gap |
|---|---|---|---|
| 0.00–0.50 | 74 |  56.8% | +0.21 |
| 0.50–0.60 | 27 |  59.3% | +0.05 |
| 0.60–0.70 | 29 |  51.7% | -0.14 |
| 0.70–0.80 | 40 |  90.0% | +0.15 |
| 0.80–0.90 | 65 |  81.5% | -0.04 |
| 0.90–1.00 | 301 |  94.0% | -0.01 |
| 1.00 | 225 | 100.0% | +0.00 |

**Expected calibration error: 0.042** — the average distance between stated confidence and actual accuracy, weighted by how many answers fall in each bucket. Lower is better.

### `llm`

| confidence | answers | accuracy | gap |
|---|---|---|---|
| 0.60–0.70 | 5 |  20.0% | -0.40 |
| 0.70–0.80 | 76 |  53.9% | -0.16 |
| 0.80–0.90 | 159 |  68.6% | -0.12 |
| 0.90–1.00 | 377 |  95.5% | +0.04 |
| 1.00 | 144 | 100.0% | +0.00 |

**Expected calibration error: 0.061** — the average distance between stated confidence and actual accuracy, weighted by how many answers fall in each bucket. Lower is better.

## Does confidence drop where the answer is genuinely unclear?

The corpus contains rows written to be routable two ways. If the confidence number is doing real work, it should be visibly lower on those.

| model | clean rows | ambiguous rows | difference |
|---|---|---|---|
| `jev` | 0.977 | 0.586 | **-0.390** |
| `llm` | 0.912 | 0.870 | **-0.043** |

*Mean reported confidence on `department`. A negative difference is the behaviour you want — and is what makes a routing threshold possible.*

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
| **technical** | 9 | 67 | 0 |
| **sales** | 0 | 0 | 47 |

*Counted against `true_department` only, so an ambiguous row answered with its `alt_department` appears off the diagonal here while still counting as correct in the accuracy table. The matrix is for seeing which pairs get confused, not for re-deriving the score.*

## Latency and cost, measured here

Wall clock from Johannesburg, both models in the same run, over the same connection. **Not** inference time, and not comparable to any published figure.

| model | cold call | warm median | warm p95 | in tokens (mean) | cost / 1 000 classifications |
|---|---|---|---|---|---|
| `jev` | 1177 ms | 417 ms | 768 ms | 578 | **$0.024** |
| `llm` | 9679 ms | 1512 ms | 4394 ms | 436 | **$0.291** |

*Prices used: Jev $0.042/M input, output free; gpt-4.1-mini $0.4/M input and $1.6/M output.*

## Where the two models disagree on department

| id | ambiguous | true | jev | llm | who was right |
|---|---|---|---|---|---|
| ENQ-0058 | yes | technical | technical (0.27) | billing (0.90) | jev, llm |
| ENQ-0061 | yes | billing | billing (0.81) | technical (0.80) | jev, llm |
| ENQ-0108 | yes | technical | technical (0.43) | billing (0.80) | jev, llm |
| ENQ-0127 | yes | technical | technical (0.33) | billing (0.80) | jev, llm |
| ENQ-0178 | no | sales | billing (0.69) | sales (0.80) | llm |

*5 disagreements. Confidence in brackets.*

