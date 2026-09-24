# Does confidence tell you when to escalate?

Replayed offline over 200 messages that both models answered. No API calls; every policy below is a different way of reading the same run.

Scored over 761 answers (spam rows carry no department, urgency or frustration and are skipped for those).

## The four policies

| policy | accuracy | cost / 1 000 messages | mean latency |
|---|---|---|---|
| Jev alone | **88.0%** | **$0.024** | 417 ms |
| GPT-4.1-mini alone | 86.1% | $0.291 | 1512 ms |
| Confidence-routed cascade (best, T=0.70) | 89.2% | $0.180 | 1226 ms |
| Oracle — always pick the model that was right | 92.0% | $0.315 | 1930 ms |

*The oracle cannot be built. It is here to bound how much any routing policy could ever be worth.*

**Escalating on low confidence buys +1.2 points for 7.4× the cost of Jev alone.** Perfect routing would be worth +3.9 points, so confidence-based routing captures 30% of what is actually available.

## Per-field cascade, across thresholds

Take the LLM's answer only for the specific fields Jev was unsure about.

| threshold | fields escalated | messages touching the LLM | accuracy | cost / 1 000 |
|---|---|---|---|---|
| ≥ 0.50 | 9.7% | 32.0% | 89.0% | $0.117 |
| ≥ 0.60 | 13.3% | 42.5% | 88.8% | $0.148 |
| ≥ 0.70 | 17.1% | 53.5% | 89.2% | $0.180 |
| ≥ 0.80 | 22.3% | 61.5% | 88.8% | $0.203 |
| ≥ 0.90 | 30.9% | 75.0% | 88.7% | $0.243 |
| ≥ 0.95 | 49.4% | 92.0% | 88.0% | $0.292 |

## Why it does not help: the models are good at different things

| field | Jev | GPT-4.1-mini |
|---|---|---|
| `department` | 99.5% | **100.0%** |
| `urgency` | 64.7% | **76.5%** |
| `is_spam` | **100.0%** | 99.0% |
| `frustration` | **87.2%** | 67.9% |

Jev being unsure does not mean the LLM will be right. Where Jev is weakest the LLM is better, but where Jev is strongest the LLM is much worse — so escalating Jev's uncertain answers hands some of them to a model that is worse at that particular question.

**Confidence tells you when to ask a human. It does not tell you when to ask a bigger model.** Those are different questions, and only the first one is answered by a number that reflects the model's own uncertainty.

