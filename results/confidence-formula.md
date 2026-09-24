# Is `confidence` just arithmetic on the probabilities?

Testing `confidence == (n x peak - 1) / (n - 1)` against every answer in `results/raw.jsonl`.

| question | primitive | answers | mean error | max error | exact | within rounding |
|---|---|---|---|---|---|---|
| `department` | Choice (3) | 200 | 0.00168 | 0.0150 | 78% | 100% |
| `urgency` | Score (3) | 200 | 0.02100 | 0.4900 | 40% | 86% |
| `is_spam` | Choice (2) | 200 | 0.00505 | 0.0100 | 50% | 100% |
| `frustration` | Score (3) | 200 | 0.00348 | 0.0150 | 50% | 100% |

*"Exact" means the reported confidence equals the formula to the last digit. "Within rounding" allows for the probabilities being reported to two decimals, which is the only slack the formula should need if it is the whole story.*

## Where it does not hold

| reported | peak formula | probabilities |
|---|---|---|
| **0** | 0.490 | 0: 0.66, 1: 0.01, 2: 0.33 |
| **0.41** | 0.685 | 0: 0.79, 1: 0.03, 2: 0.18 |
| **0** | 0.265 | 0: 0.51, 1: 0.18, 2: 0.31 |
| **0** | 0.250 | 0: 0.5, 1: 0.05, 2: 0.45 |
| **0.42** | 0.670 | 0: 0.78, 1: 0.04, 2: 0.18 |

Every one of these is a **Score**, and in every one the reported confidence is *lower* than the peak-only formula. The mass is spread across adjacent levels, and Jev is accounting for that spread. TypeSafe's published formula is stated for a Choice, so this is not a contradiction - it says Score confidence measures dispersion across an ordered scale rather than the height of the winning level.

## Why this matters for routing

Confidence is computed from the distribution over **these options for this input**. It has no access to a second model, so it cannot predict whether a bigger model would do better - only how concentrated its own answer is. That is the mechanism behind the cascade result in `cascade.md`: escalating low-confidence answers to an LLM bought little, because low confidence marks an ambiguous input rather than a question another model happens to be good at.

