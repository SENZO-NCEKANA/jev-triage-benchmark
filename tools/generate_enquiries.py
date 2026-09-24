#!/usr/bin/env python3
"""
Generate a labelled corpus of inbound customer enquiries for the Jev benchmark.

WHY THIS EXISTS
---------------
Running two models over the same messages tells you how often they agree.
Agreement is not accuracy: two models can agree and both be wrong, and a
model that is confidently wrong looks identical to one that is confidently
right unless you already know the answer.

So every message here is generated FROM its label rather than labelled after
the fact. The template decides the department; the tone wrapper decides the
frustration level; the urgency clause decides the urgency. The label is not a
judgement call made by a human reading the text afterwards - it is the recipe
the text was built from. That makes accuracy measurable and, more importantly,
makes CALIBRATION measurable: we can bucket predictions by the confidence the
model reported and check whether the 0.9 bucket is really right 90% of the time.

Roughly 15% of the corpus is deliberately ambiguous - messages that a
reasonable human would route two different ways. Those rows carry a second
acceptable department in `alt_department` and are flagged. They are the
interesting ones: a well-calibrated model should report LOWER confidence on
them. If confidence is flat across clean and ambiguous rows, the number is
decoration rather than a signal worth thresholding on.

Context is South African: ZAR, 15% VAT, local banks and couriers, load-shedding,
Africa/Johannesburg business hours. The company is fictional (Kopano, a booking
and payments platform for small businesses) and so is every name, address and
reference number. No real customer data goes near this repo.

Usage:
    python3 tools/generate_enquiries.py                 # 200 rows -> sample-data/
    python3 tools/generate_enquiries.py --count 50
    python3 tools/generate_enquiries.py --seed 7
"""

import argparse
import csv
import json
import random
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Label spaces come from schema.py, which is also what both models are asked.
# Defining them twice is how a benchmark quietly stops comparing like with like:
# the corpus would be labelled against one set of words and the models judged
# against another.
# ---------------------------------------------------------------------------

from schema import URGENCY_LEVELS, FRUSTRATION_LEVELS  # noqa: E402

# ---------------------------------------------------------------------------
# Slot vocabulary
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Thabo", "Lerato", "Sipho", "Nandi", "Ayanda", "Pieter", "Riaan", "Anelisa",
    "Fatima", "Yusuf", "Karabo", "Zanele", "Johan", "Shanice", "Mpho", "Tebogo",
    "Naledi", "Willem", "Bongani", "Precious", "Nomsa", "Devan", "Kagiso",
    "Chantelle", "Sibusiso", "Marieke", "Lwazi", "Rushda", "Tumi", "Andries",
]

LAST_NAMES = [
    "Mokoena", "Naidoo", "van der Merwe", "Dlamini", "Botha", "Khumalo", "Pillay",
    "Nkosi", "du Plessis", "Mahlangu", "Abrahams", "Zwane", "Coetzee", "Maseko",
    "Jacobs", "Ndlovu", "Fourie", "Radebe", "Petersen", "Mthembu",
]

COMPANIES = [
    "Kasi Fresh Produce", "Sandton Dental Studio", "Bay Road Physio",
    "Umhlanga Nail Bar", "Braamfontein Print Co", "Hoedspruit Safari Tours",
    "Table View Driving School", "Mamelodi Auto Spares", "Gqeberha Pet Grooming",
    "Vaal Event Hire", "Klerksdorp Hardware", "Sea Point Yoga",
    "Polokwane Tyre Fitment", "Soweto Sound Hire", "Durbanville Bakery",
]

CITIES = [
    "Johannesburg", "Cape Town", "Durban", "Pretoria", "Gqeberha", "Bloemfontein",
    "Polokwane", "Mbombela", "East London", "Kimberley", "Soweto", "Stellenbosch",
]

BANKS = ["FNB", "Capitec", "Nedbank", "Standard Bank", "Absa", "TymeBank", "Discovery Bank"]
GATEWAYS = ["PayFast", "Ozow", "SnapScan", "Yoco", "Peach Payments"]
COURIERS = ["The Courier Guy", "Aramex", "PostNet", "Pargo"]
PLANS = ["Starter", "Growth", "Business", "Enterprise"]
BROWSERS = ["Chrome", "Safari", "Edge", "Firefox"]

# ---------------------------------------------------------------------------
# Message bodies. Each one is tied to exactly one department by construction.
# `urgencies` restricts which urgency clauses make sense - a site that is down
# cannot sensibly be "not urgent", and a pricing question is rarely an outage.
# ---------------------------------------------------------------------------

Template = tuple  # (subject, body, allowed urgency indices)

BILLING = [
    ("Double charge on my account",
     "I was billed twice for the {plan} plan this month. My {bank} statement shows two debits of R{amount} on {date}, both referencing {ref}. Please reverse one of them.",
     [1, 2]),
    ("Debit order failed",
     "The monthly debit order for {company} bounced again. My {bank} account had the funds on {date}, so I do not understand why it came back. Invoice {invoice} is still showing unpaid.",
     [1, 2]),
    ("Request for a VAT invoice",
     "Could you send me a proper tax invoice for {invoice}? My bookkeeper needs the VAT number and the 15% shown separately. The amount was R{amount}.",
     [0, 1]),
    ("Refund not received",
     "I cancelled on {date} and was told the R{amount} would be back within 5 working days. It has now been {days} days and nothing has reflected in my {bank} account.",
     [1, 2]),
    ("Wrong amount charged",
     "My invoice {invoice} says R{amount} but I am on the {plan} plan which was quoted at a different price. Please explain the difference.",
     [0, 1]),
    ("Payment shows as pending",
     "I paid via {gateway} on {date} and it left my account, but the dashboard for {company} still says payment outstanding. Reference {ref}.",
     [1, 2]),
    ("Please cancel my subscription and stop billing",
     "I want to cancel the {plan} plan for {company} effective end of month. Please confirm no further debit orders will go off.",
     [0, 1]),
    ("Charged after cancelling",
     "I cancelled {days} days ago and you have taken another R{amount} off my {bank} card. I have the cancellation email.",
     [1, 2]),
    ("Statement does not match",
     "Can someone reconcile my account? Invoice {invoice} for R{amount} appears twice on my statement but only once in my bank records.",
     [0, 1]),
    ("Change payment method",
     "My {bank} card expired. How do I load a new card for {company} before the next debit order on {date}?",
     [0, 1]),
]

TECHNICAL = [
    ("Cannot log in",
     "Nobody at {company} can log in since this morning. We enter the password, the page reloads, and we are back at the login screen. Tried {browser} and a different laptop.",
     [1, 2]),
    ("Bookings not coming through",
     "Customers say they are booking but nothing arrives in our dashboard. The last booking we can see is from {date}. We are in {city} if the region matters.",
     [2]),
    ("Error 500 when saving",
     "Every time I save a service under {company} I get a 500 error. Reference {ref} appeared on the error screen.",
     [1, 2]),
    ("{gateway} integration broken",
     "Our {gateway} integration stopped taking payments at checkout. Customers get as far as the card screen and then it fails silently.",
     [2]),
    ("Site slow during load-shedding",
     "During Stage 4 our shop page takes 30 seconds or more to load. Our fibre is fine and other sites are quick, so I think something is timing out on your side.",
     [1, 2]),
    ("SMS reminders not sending",
     "Appointment reminders have not gone out to any of our clients since {date}. The dashboard says sent, the clients received nothing.",
     [1, 2]),
    ("Calendar sync duplicating entries",
     "Every booking now appears three times in my Google Calendar. Started after the update on {date}.",
     [0, 1]),
    ("Reports export is empty",
     "When I export the monthly report for {company} the CSV downloads but has only headers, no rows. Using {browser} on Windows.",
     [0, 1]),
    ("Password reset email never arrives",
     "I have requested a reset {days} times for {email} and nothing arrives, including in spam.",
     [1, 2]),
    ("Photos will not upload",
     "Uploading images to our gallery fails at about 80% every time. Files are roughly 2MB, taken on a phone.",
     [0, 1]),
]

SALES = [
    ("Pricing for a larger team",
     "We are {company} in {city} and have {days} staff who would each need a login. What would the {plan} plan cost us per month, and is there a discount annually?",
     [0, 1]),
    ("Can I see a demo",
     "I run a small practice and I am comparing options. Could someone walk me through the booking side before I commit? I am in {city}.",
     [0, 1]),
    ("Upgrade from Starter",
     "We are outgrowing the Starter plan at {company}. What does moving to {plan} involve and does it happen immediately?",
     [0, 1]),
    ("Does it do stock as well",
     "Before I sign up - does the platform handle stock levels, or only bookings? We sell products alongside our services.",
     [0]),
    ("Multi-branch question",
     "We are opening a second branch in {city}. Can one account run two locations with separate calendars, and what does that cost?",
     [0, 1]),
    ("Trial extension",
     "My 14-day trial ends on {date} but our busy season only starts next month. Could I get a short extension before deciding?",
     [0, 1]),
    ("Switching from a competitor",
     "We currently use another system and have about 900 client records. Do you help with importing that, and is there a setup fee?",
     [0, 1]),
    ("Invoice for procurement",
     "Our procurement team at {company} needs a formal quotation on a letterhead for the {plan} plan before they will approve the purchase. Can you send one?",
     [0, 1]),
]

# ---------------------------------------------------------------------------
# Deliberately ambiguous. A reasonable human routes these two ways, so they
# carry a second acceptable answer and the scorer accepts either. These exist
# to test whether reported confidence actually drops where the answer is
# genuinely unclear.
# ---------------------------------------------------------------------------

AMBIGUOUS = [
    ("billing", "technical",
     "Payment page failing - and I have been charged",
     "Checkout throws an error every time, but three of the attempts still came off my {bank} card at R{amount} each. So I have no booking and three charges.",
     [2]),
    ("technical", "billing",
     "Upgrade did not apply",
     "I paid to move to the {plan} plan on {date}, the money is gone, but the account still shows Starter and the extra logins are missing.",
     [1, 2]),
    ("sales", "billing",
     "What happens to my existing credit if I upgrade",
     "I am thinking about upgrading to {plan}, but I have already paid for the current month. Would that be pro-rated or do I lose it?",
     [0, 1]),
    ("billing", "sales",
     "Cancelling because it is too expensive",
     "R{amount} a month is more than {company} can carry right now. Cancel us - unless there is a cheaper plan you can move us to.",
     [0, 1]),
    ("technical", "sales",
     "Does the export actually work",
     "I am still on trial and the CSV export gives me an empty file. Is that a bug or is export only on the paid plans? It decides whether I sign up.",
     [0, 1]),
    ("billing", "technical",
     "Invoice download broken",
     "I need invoice {invoice} for my bookkeeper and the download button does nothing in {browser}. Can someone email it to me instead.",
     [0, 1]),
    ("sales", "technical",
     "Migration question before we commit",
     "We would move about 900 records across from our old system. Has that import ever broken for anyone, and who fixes it if it does?",
     [0, 1]),
    ("technical", "billing",
     "Locked out after failed payment",
     "The account for {company} is locked and it says payment failed, but {gateway} shows the R{amount} as successful on {date}. We cannot take bookings.",
     [2]),
]

# ---------------------------------------------------------------------------
# Spam. Labelled is_spam = yes and excluded from department scoring, since
# there is no honest correct department for them.
# ---------------------------------------------------------------------------

SPAM = [
    ("Re: Your website ranking",
     "Dear Sir/Madam, I reviewed your website and found 7 critical SEO errors keeping you off page 1 of Google. We guarantee first page results in 30 days. Reply YES for a free audit.",),
    ("Business funding approved",
     "CONGRATULATIONS! Your business qualifies for R750 000 in unsecured funding. No credit check. Limited slots this month. WhatsApp us now to claim.",),
    ("Crypto opportunity",
     "Hi, I noticed you run a business. I help owners earn R15 000 per week passively with AI trading bots. Minimum start R5 000. Interested?",),
    ("Invoice attached",
     "Please find attached the outstanding invoice for immediate payment. Kindly confirm receipt and process payment to the updated banking details below.",),
    ("Partnership proposal",
     "Greetings, I represent an investor seeking local partners for a mutually beneficial arrangement of USD 4.5 million. Your reply is treated in strict confidence.",),
    ("Cheap web design",
     "We build websites for R1 999 once off. WhatsApp 24/7. Also logos, flyers, business cards, company registration, tax clearance.",),
]

# ---------------------------------------------------------------------------
# Tone and urgency wrappers. These are what set the frustration and urgency
# labels, so they are kept clearly separate from the department bodies.
# ---------------------------------------------------------------------------

OPENERS = {
    0: ["Good day,", "Hi there,", "Hello,", "Morning,", "Good afternoon,"],
    1: ["Hi,", "Good day,", "Hello,", "Hi again,"],
    2: ["", "Right.", "This is the last time I am writing about this.", "Seriously?"],
}

# Prefixes carry a minimum urgency for the same reason closers do, and the
# reason is worth stating because it was missed the first time round.
#
# Every frustration prefix originally asserted that the sender had ALREADY been
# waiting - "Nobody has come back to me", "Four emails. FOUR." A sender who has
# chased four times is not describing a message that can wait, so pairing those
# words with urgency 0 produced text contradicting its own label: 15 rows in the
# first corpus, plus 5 labelled both "Very angry" and "Not urgent".
#
# It was caught by a model getting urgency "wrong" on 3 of the first 5 rows
# while getting the other three axes right - which turned out to be the model
# being right against a bad label. An unusable urgency score is exactly what
# ground-truth labelling is supposed to prevent, so the gate goes here: anger
# that claims prior waiting implies urgency >= 1, and anger that does not is
# free to appear anywhere.
TONE_PREFIX = {
    0: [("", 0), ("Hope you are well. ", 0), ("Sorry to bother you. ", 0)],
    1: [
        ("I am not happy about this. ", 0),
        ("This is frustrating. ", 0),
        ("This is the second time I am writing about this. ", 1),
        ("I have been waiting on a reply since last week. ", 1),
        ("I am starting to lose patience here. ", 1),
        ("Nobody has come back to me. ", 1),
    ],
    2: [
        ("This is now completely unacceptable. ", 1),
        ("I have had ENOUGH. ", 1),
        ("Four emails. FOUR. And not one reply. ", 1),
        ("I am beyond frustrated with this service. ", 1),
    ],
}

# Each closer carries a minimum urgency. Without that gate the generator
# produced "Whenever you get a chance. Please come back to me today." - the
# urgency clause and the closer contradicting each other inside one message,
# which makes the urgency label indefensible. Anger and time pressure are
# separate axes and the wording has to keep them separate.
TONE_SUFFIX = {
    0: [
        ("Thanks in advance.", 0),
        ("No rush at all, thank you.", 0),
        ("Appreciate the help.", 0),
        ("Thank you kindly.", 0),
        ("Please let me know as soon as you can.", 1),
    ],
    1: [
        ("Can someone please take ownership of this.", 0),
        ("Please let me know what the next step is.", 0),
        ("I would like this sorted out.", 0),
        ("I would appreciate an actual answer this time.", 1),   # "this time" = has asked before
        ("Please escalate if you cannot help.", 1),
        ("Please come back to me today.", 2),                    # a same-day deadline
        ("I need someone on this now, not tomorrow.", 2),
    ],
    2: [
        ("I want a manager to phone me. Not another automated reply.", 1),
        ("I am reporting this to my bank as a dispute and moving to a competitor.", 1),
        ("Fix it or refund me in full. Those are the only two options.", 2),
        ("If this is not resolved today I am cancelling and telling every business owner I know.", 2),
        ("Every minute of this is costing me customers. Sort it out.", 2),
    ],
}

URGENCY_CLAUSE = {
    0: ["", "Whenever you get a chance. ", "No deadline on my side. "],
    1: [
        "I need this sorted before the end of the week. ",
        "Month-end is coming and I need it right before then. ",
        "Please can someone look at it in the next day or two. ",
    ],
    2: [
        "We cannot trade until this is fixed. ",
        "We have customers standing in front of us right now. ",
        "This is costing us money every hour it stays broken. ",
        "We open in two hours and this has to work by then. ",
    ],
}

CHANNELS = ["email", "web form", "whatsapp"]


def slots(rng):
    """One bag of random values, reused across every placeholder in a message."""
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    return {
        "name": f"{first} {last}",
        "first": first,
        "email": f"{first.lower()}.{last.split()[-1].lower()}@example.co.za",
        "company": rng.choice(COMPANIES),
        "city": rng.choice(CITIES),
        "bank": rng.choice(BANKS),
        "gateway": rng.choice(GATEWAYS),
        "courier": rng.choice(COURIERS),
        "plan": rng.choice(PLANS),
        "browser": rng.choice(BROWSERS),
        "amount": f"{rng.randrange(199, 8500):,}".replace(",", " "),
        "invoice": f"INV-2026-{rng.randrange(1000, 9999)}",
        "order": f"KPN-{rng.randrange(10000, 99999)}",
        "ref": f"{rng.choice('ABCDEFGH')}{rng.randrange(100000, 999999)}",
        "date": f"{rng.randrange(1, 28)} September",
        "days": str(rng.randrange(2, 21)),
    }


def first_sentences(text, n):
    """Trim to whole sentences. An earlier version cut at a fixed word count and
    produced 'My invoice INV-2026-2535 says R687 but' - the billing signal
    removed, while the row still claimed the billing label. Never truncate
    anywhere the label might live."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:n])


def whatsappify(body, prefix, suffix, rng):
    """WhatsApp is shorter and sloppier, but the tone prefix and closing are kept
    in full because they are what carry the frustration label. Only the factual
    body is shortened, and only at a sentence boundary.

    The label is deliberately identical across channels: it tests whether either
    model is thrown by register rather than by meaning."""
    text = f"{prefix}{first_sentences(body, rng.randrange(1, 3))} {suffix}".strip()
    if rng.random() < 0.6:
        text = text.lower()
    for full, short in (("please", "pls"), ("thanks", "thx"), ("and ", "& ")):
        if rng.random() < 0.35:
            text = text.replace(full, short)
    return text.rstrip(" .,") + rng.choice(["", "", "", "??", "...", " 🙏"])


def build_row(idx, rng):
    """Pick a template, then wrap it in tone and urgency. The label comes from
    the recipe, never from reading the finished text."""
    roll = rng.random()

    # --- spam -------------------------------------------------------------
    if roll < 0.08:
        subject, body = rng.choice(SPAM)
        channel = rng.choices(CHANNELS, weights=[6, 3, 1])[0]
        return {
            "id": f"ENQ-{idx:04d}",
            "channel": channel,
            "from_name": rng.choice(FIRST_NAMES),
            "subject": subject,
            "message": body,
            # Spam has no honest department, and no honest urgency or
            # frustration either. The first version filled these with 0, which
            # is not "unknown" but a claim - and a false one: scam mail says
            # things like "outstanding invoice for immediate payment", so both
            # models read urgency into it and were marked wrong against a label
            # that had simply been invented. Blank means unscoreable, and the
            # scorer skips these rather than counting them against anybody.
            "true_department": "",
            "alt_department": "",
            "true_urgency": "",
            "true_urgency_label": "",
            "true_frustration": "",
            "true_frustration_label": "",
            "true_is_spam": "yes",
            "is_ambiguous": "no",
        }

    # --- ambiguous --------------------------------------------------------
    if roll < 0.23:
        dept, alt, subject, body, urgencies = rng.choice(AMBIGUOUS)
        ambiguous = "yes"
    # --- clean ------------------------------------------------------------
    else:
        dept = rng.choices(["billing", "technical", "sales"], weights=[35, 40, 25])[0]
        pool = {"billing": BILLING, "technical": TECHNICAL, "sales": SALES}[dept]
        subject, body, urgencies = rng.choice(pool)
        alt = ""
        ambiguous = "no"

    s = slots(rng)
    urgency = rng.choice(urgencies)

    # Frustration correlates with urgency but is not determined by it - calm
    # people do have emergencies, and people rage about trivial things.
    # The one combination ruled out is "Very angry" with "Not urgent": every way
    # of writing real fury implies the sender wants it dealt with now, so that
    # pairing only ever produced incoherent text.
    frustration = rng.choices(
        [0, 1, 2],
        weights={0: [75, 25, 0], 1: [40, 45, 15], 2: [20, 45, 35]}[urgency],
    )[0]

    prefix = rng.choice([t for t, min_u in TONE_PREFIX[frustration] if min_u <= urgency])
    filled = body.format(**s)
    # Only closers whose minimum urgency this message meets, so a "not urgent"
    # enquiry can never end by demanding a reply today.
    suffix = rng.choice([t for t, min_u in TONE_SUFFIX[frustration] if min_u <= urgency])

    channel = rng.choices(CHANNELS, weights=[5, 3, 2])[0]
    if channel == "whatsapp":
        message = whatsappify(filled, prefix, suffix, rng)
    else:
        opener = rng.choice(OPENERS[frustration])
        body_text = (
            f"{prefix}{filled} "
            f"{rng.choice(URGENCY_CLAUSE[urgency])}{suffix}"
        ).strip()
        # Opener on its own line - "Hello, Nobody has come back to me." was
        # a capital letter mid-sentence in the first run.
        head = f"{opener}\n\n" if opener else ""
        message = f"{head}{body_text}\n\n{s['first']}\n{s['company']}".strip()

    return {
        "id": f"ENQ-{idx:04d}",
        "channel": channel,
        "from_name": s["name"],
        "subject": subject.format(**s),
        "message": message,
        "true_department": dept,
        "alt_department": alt,
        "true_urgency": urgency,
        "true_urgency_label": URGENCY_LEVELS[urgency],
        "true_frustration": frustration,
        "true_frustration_label": FRUSTRATION_LEVELS[frustration],
        "true_is_spam": "no",
        "is_ambiguous": ambiguous,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42, help="fixed so the corpus is reproducible")
    ap.add_argument("--out", default="sample-data")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    rows = [build_row(i + 1, rng) for i in range(args.count)]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    fields = list(rows[0].keys())
    with (out / "enquiries.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    with (out / "enquiries.json").open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)

    # --- distribution report, so a skewed corpus is visible immediately ----
    def tally(key):
        counts = {}
        for r in rows:
            counts[str(r[key])] = counts.get(str(r[key]), 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    print(f"{len(rows)} enquiries -> {out/'enquiries.csv'} and {out/'enquiries.json'}\n")
    for key in ("true_department", "true_urgency_label", "true_frustration_label",
                "true_is_spam", "is_ambiguous", "channel"):
        pretty = ", ".join(f"{k or '(spam)'}: {v}" for k, v in tally(key).items())
        print(f"  {key:24} {pretty}")

    scoreable = sum(1 for r in rows if r["true_is_spam"] == "no")
    print(f"\n  department-scoreable rows: {scoreable}  "
          f"(spam rows carry no department and are excluded)")


if __name__ == "__main__":
    main()
