# The post

The write-up that accompanies this benchmark, kept with the code so the claims and their sources stay together.

**Image:** `docs/charts/confidence-spread.png` — 69 distinct confidence values against 11 reads at thumbnail size and makes the argument before anyone reads a word.

---

## Post

```
🚀 A new AI model shipped this month claiming 40–200× faster and ~400× cheaper than an LLM at classification. Nobody had checked independently, so I built a benchmark.

Jev, from @TypeSafe AI, doesn't write text. It answers structured questions and returns typed decisions with a confidence score.

I generated 200 South African customer enquiries carrying known correct answers, then ran Jev and GPT-4.1-mini over identical inputs. The known answers are the point — two models can agree and both be wrong.

📊 Measured from Johannesburg:

🔹 92.9% accurate vs 89.9%
🔹 11.8× cheaper — $0.026 vs $0.308 per 1 000 classifications
🔹 3.6× faster — 415ms vs 1 496ms
🔹 Jev lost one of the four questions

Not the 40–200× on the box. But GPT-4.1-mini is already small and cheap, which makes it the hardest comparison available — and Jev won it on both anyway.

📢 The part I didn't expect:

Confidence tells you when to ask a human. It does not tell you when to ask a bigger model.

Routing uncertain answers to a person works — 89% auto-filed at 95.7% accuracy. Routing those same answers to GPT instead made accuracy WORSE, at 3.4× the cost.

Jev used 69 distinct confidence values across 800 answers. GPT-4.1-mini used 11, and said "0.9" 299 times — after I explicitly instructed it to use the full range.

⚠️ I also got something wrong, publicly.

I first reported Jev was weak on urgency: 64.7%. Then I read TypeSafe's own guidance on writing score levels — describe situations, not degrees. Mine were degrees. I rewrote three sentences, changed nothing else, and urgency went to 85%. The three untouched questions didn't move.

The weakness was my question, not the model.

Both runs are in the repo so anyone can check.

🛠️ Python • n8n • Jev • GPT-4.1-mini

Repo in the comments 👇

#AI #AIEngineering #MachineLearning #Benchmarking #Automation #n8n #BuildInPublic #DataScience
```

**First comment:**

```
👇 Repo — the corpus generator, both runs, and every number recomputable:

https://github.com/SENZO-NCEKANA/jev-triage-benchmark

The two worth reading: results/cascade.md, where escalating to a bigger model makes accuracy worse, and the urgency correction, where rewriting three sentences moved a result 20 points while three untouched controls stayed put.
```

---

## Where each claim comes from

| Claim | Source |
|---|---|
| 92.9% vs 89.9% | [`results/cascade.md`](results/cascade.md) |
| $0.026 vs $0.308 per 1 000 | [`results/report.md`](results/report.md) |
| 415 ms vs 1 496 ms, warm | [`results/report.md`](results/report.md) |
| 89% auto-filed at 95.7% | [`results/report.md`](results/report.md) |
| Escalation is worse, 3.4× cost | [`results/cascade.md`](results/cascade.md) |
| 69 vs 11 distinct confidence values | [`results/report.md`](results/report.md) |
| urgency 64.7% → 85.0% | [`results/report.urgency-v1.md`](results/report.urgency-v1.md) → [`results/report.md`](results/report.md) |

Nothing in the post is quoted from marketing. TypeSafe's published 40–200× and ~400× appear only as the claim being tested, and are presumably measured against frontier models rather than GPT-4.1-mini.

---

## Questions this usually gets

**Why not compare against a bigger model?**

Deliberately the hardest comparison available. GPT-4.1-mini is already small, fast and cheap, so the gap here is the one that survives a tough opponent rather than the flattering one.

**200 messages is a small sample.**

Agreed, and the README says so. 200 comfortably separates a −0.395 confidence drop from a −0.046 one. It does not separate 99.5% from 99.5% on department, or 85% from 87% on urgency — those are ties, not results.

**How do you know your labels are right?**

Every message is generated *from* its label rather than labelled afterwards: a template fixes the department, a tone wrapper fixes the frustration level. The label is the recipe, not a later judgement. That said, the labels were wrong three separate times during this build, and the tell was identical each time — two independent models agreeing against the ground truth.

**Would you run this in production?**

For triage where a misroute costs someone a forward, yes, at a 0.70 threshold with a person on the other branch. For anything irreversible, no — the threshold should scale with the stakes, which is what TypeSafe's own three-band guidance says, and it needs a labelled sample from that domain first.

**Isn't this a tutorial with extra steps?**

The claims were a week old and unchecked. Running both models over identical labelled inputs and publishing the disagreements, the costs, and a retracted finding of my own is data rather than a walkthrough. Clone it and the numbers regenerate.
