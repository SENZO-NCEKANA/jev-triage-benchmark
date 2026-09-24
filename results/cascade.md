# Does confidence tell you when to escalate?

Replayed offline over 200 messages that both models answered. No API calls; every policy below is a different way of reading the same run.

Scored over 761 answers (spam rows carry no department, urgency or frustration and are skipped for those).

## The four policies

| policy | accuracy | cost / 1 000 messages | mean latency |
|---|---|---|---|
| Jev alone | **92.9%** | **$0.026** | 415 ms |
| GPT-4.1-mini alone | 89.9% | $0.308 | 1496 ms |
| Confidence-routed cascade (best, T=0.50) | 92.2% | $0.089 | 721 ms |
| Oracle — always pick the model that was right | 95.5% | $0.334 | 1910 ms |

*The oracle cannot be built. It is here to bound how much any routing policy could ever be worth.*

**Escalating on low confidence makes it worse: -0.7 points, for 3.4× the cost of Jev alone.** Even the best threshold tested loses accuracy. Perfect routing would have been worth +2.6 points, so the signal is not merely weak here - following it moves in the wrong direction.

## Per-field cascade, across thresholds

Take the LLM's answer only for the specific fields Jev was unsure about.

| threshold | fields escalated | messages touching the LLM | accuracy | cost / 1 000 |
|---|---|---|---|---|
| ≥ 0.50 | 6.0% | 20.5% | 92.2% | $0.089 |
| ≥ 0.60 | 8.8% | 29.5% | 92.1% | $0.117 |
| ≥ 0.70 | 10.9% | 36.0% | 91.6% | $0.137 |
| ≥ 0.80 | 15.8% | 47.0% | 91.7% | $0.171 |
| ≥ 0.90 | 24.0% | 61.5% | 91.2% | $0.216 |
| ≥ 0.95 | 43.2% | 81.0% | 90.4% | $0.276 |

## Why it does not help: the models are good at different things

| field | Jev | GPT-4.1-mini |
|---|---|---|
| `department` | 99.5% | 99.5% |
| `urgency` | 85.0% | **87.2%** |
| `is_spam` | **100.0%** | 99.0% |
| `frustration` | **86.6%** | 73.3% |

Jev being unsure does not mean the LLM will be right. Where Jev is weakest the LLM is better, but where Jev is strongest the LLM is much worse — so escalating Jev's uncertain answers hands some of them to a model that is worse at that particular question.

**Confidence tells you when to ask a human. It does not tell you when to ask a bigger model.** Those are different questions, and only the first one is answered by a number that reflects the model's own uncertainty.

