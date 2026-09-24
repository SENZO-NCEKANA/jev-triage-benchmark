"""
The single source of truth for what both models are asked.

WHY THIS FILE EXISTS
--------------------
The benchmark's entire claim rests on the two models having been asked the
*same question*. If Jev's criteria say "Payments, invoices, refunds" and the
LLM prompt says "anything about money", the comparison measures the wording,
not the models.

So the label spaces and the criteria strings are defined once, here, and
imported by all three places that need them:

    generate_enquiries.py   - to label the corpus
    run_benchmark.py        - to ask Jev, and to ask the LLM
    score_results.py        - to score both against the labels

Nothing in this file is retyped anywhere else. If a criterion changes, it
changes for the corpus and for both models at the same moment, or the run is
not comparable and the numbers are not publishable.
"""

# ---------------------------------------------------------------------------
# Label spaces
# ---------------------------------------------------------------------------

DEPARTMENTS = {
    "billing":   "Payments, invoices, refunds, pricing disputes, failed debit orders",
    "technical": "Bugs, errors, outages, logins, integrations, anything broken",
    "sales":     "Pricing questions before buying, upgrades, demos, new accounts",
}

SPAM = {
    "no":  "A real customer or prospect contacting the business",
    "yes": "Unsolicited marketing, scams, cold outreach or phishing",
}

URGENCY_LEVELS = ["Not urgent", "Needs attention this week", "Blocking business right now"]
FRUSTRATION_LEVELS = ["Calm", "Frustrated", "Very angry"]

INSTRUCTIONS = {
    "department":  "Which team should handle this message?",
    "urgency":     "How quickly does this need a response?",
    "is_spam":     "Is this a genuine customer enquiry or unsolicited spam?",
    "frustration": "How frustrated is the sender?",
}

FIELDS = ("department", "urgency", "is_spam", "frustration")

# How the comparison model is named in reports. The model id itself lives in
# run_benchmark.py; this is only the label printed in tables.
LLM_LABEL = "GPT-4.1-mini"

# ---------------------------------------------------------------------------
# Jev: the four questions, asked in a single request
# ---------------------------------------------------------------------------

JEV_QUESTIONS = {
    "department": {
        "type": "choice",
        "instructions": INSTRUCTIONS["department"],
        "criteria": DEPARTMENTS,
    },
    "urgency": {
        "type": "score",
        "instructions": INSTRUCTIONS["urgency"],
        "criteria": URGENCY_LEVELS,
    },
    "is_spam": {
        "type": "choice",
        "instructions": INSTRUCTIONS["is_spam"],
        "criteria": SPAM,
    },
    "frustration": {
        "type": "score",
        "instructions": INSTRUCTIONS["frustration"],
        "criteria": FRUSTRATION_LEVELS,
    },
}


def _numbered(levels):
    return "\n".join(f"      {i} = {label}" for i, label in enumerate(levels))


def _named(criteria):
    return "\n".join(f"      {k} = {v}" for k, v in criteria.items())


# ---------------------------------------------------------------------------
# The LLM arm: the same four questions, the same criteria strings, expressed
# the way a chat model needs them.
#
# The LLM is also asked for a confidence per field. That is the sharpest
# comparison available here: Jev reports a calibrated number that falls out of
# the model, while the LLM reports a number it chooses to say. Scoring both
# against known labels shows whether those two things behave alike.
# ---------------------------------------------------------------------------

LLM_SYSTEM_PROMPT = f"""You are triaging inbound customer messages for a South African booking and payments platform.

Classify the message on four axes and reply with JSON only.

department - {INSTRUCTIONS['department']}
      one of: billing, technical, sales
{_named(DEPARTMENTS)}

urgency - {INSTRUCTIONS['urgency']}
      an integer 0-2:
{_numbered(URGENCY_LEVELS)}

is_spam - {INSTRUCTIONS['is_spam']}
      one of: yes, no
{_named(SPAM)}

frustration - {INSTRUCTIONS['frustration']}
      an integer 0-2:
{_numbered(FRUSTRATION_LEVELS)}

For each field also give a confidence between 0 and 1: how likely your answer is
to be correct. Use the full range. If a message could reasonably be routed two
ways, say so with a lower confidence rather than picking one at high confidence.

Reply with exactly this JSON shape and nothing else:

{{"department": {{"answer": "billing", "confidence": 0.0}},
 "urgency": {{"answer": 0, "confidence": 0.0}},
 "is_spam": {{"answer": "no", "confidence": 0.0}},
 "frustration": {{"answer": 0, "confidence": 0.0}}}}"""


if __name__ == "__main__":  # quick eyeball of what the LLM actually receives
    print(LLM_SYSTEM_PROMPT)
