# Citizen Petition Assistant

A citizen speaks or types, in Tamil or English. The assistant asks five
questions, checks each answer, reads everything back for confirmation, and
produces a petition as a PDF and a Word document.

It is built so that the parts a citizen depends on — whether their Aadhaar
number is right, which question comes next, what appears on the finished
document — do not depend on artificial intelligence at all.

---

## What a citizen experiences

| | |
| --- | --- |
| **1. Name** | "What is your name?" |
| **2. Age** | "What is your age?" |
| **3. Address** | "What is your full address?" |
| **4. Aadhaar number** | "Please say your 12-digit Aadhaar number." |
| **5. Grievance** | "Now please tell me your grievance, in your own words." |

Then the assistant reads everything back and waits. Nothing is produced until
the citizen says yes.

The whole conversation works by voice or by typing, and a citizen can switch
between the two at any point. Everything is available in Tamil and in English.

**If a citizen makes a mistake**, they say so — "actually my age is 31" — and the
assistant corrects that one detail without restarting. The change is recorded, so
an officer reading the file can see that a value was amended.

**If the read-back is wrong**, saying "no" does not start the interview again and
does not repeat the same list. The assistant asks which detail to change, naming
the five so the citizen does not have to invent the words. Only that detail is
cleared; it is asked again, checked again, and the read-back comes round.

**If a citizen is interrupted** — a dropped call, a closed browser — nothing is
lost. They return to the same session and carry on from where they stopped.

**If a citizen changes their mind**, "start over" clears everything and "cancel"
ends the request with nothing saved.

---

## What the system decides, and what it does not

This distinction is the design of the system, not a caveat attached to it.

### Decided by rules, written down and testable

- Which question is asked, and in what words. Every sentence the assistant says
  to a citizen was written in advance, in both languages, and reviewed. The AI
  never composes a question.
- Whether an answer is acceptable. An Aadhaar number is checked against its
  official check digit — which catches a transposed pair of digits, the commonest
  error when a number is read aloud — a PIN code against its format, an age
  against a plausible range, a date for being a real date in the past.
- What still needs to be collected.
- What appears on the finished document. Every value the citizen gave is placed
  by fixed rules, in a fixed layout.
- Whether the finished document is released. The system reads the generated file
  back and confirms every required value is present in it. If anything is
  missing, the document is withheld rather than handed over.

### Assisted by AI

- Reading an unusual reply. When a citizen answers several things at once, or
  corrects something said earlier, the AI works out which detail they meant.
- Writing the opening paragraph of the petition — the formal sentences that
  introduce the request.
- Answering a citizen's question about the form, strictly from the form's own
  description.

**The citizen's grievance is never rewritten.** It is reproduced in the petition
word for word, under a heading that says so. A petition in which the complaint
has been reworded is a different petition.

**The system does not decide eligibility, entitlement, or any legal position,**
and it does not route a petition to a department. Every document carries a note
saying it was prepared from what the citizen said and must be checked before
signing.

### If the AI is unavailable

The service continues. Every question is still asked, every answer is still
checked, and the petition is still produced using standard wording. This is not
a fallback added afterwards — it is how the system is tested. The entire
automated test suite runs with no AI service reachable at all.

---

## Handling of citizen information

- **On-premise by default.** Out of the box, nothing is sent to any outside
  service. Connecting to an external AI provider requires an explicit setting; a
  credential alone is not enough to turn it on.
- **The Aadhaar number is never sent to an AI service at all.** It is left out
  of every prompt at source rather than relying on redaction: the AI writes the
  petition's opening paragraph without being told it, and the number is placed on
  the document afterwards by fixed rules. Masking still runs at the boundary as a
  second line of defence, on both halves of every request.
- **A malformed Aadhaar number is not sent either.** There is nothing for an AI
  to interpret — it is twelve digits or it is not — so a rejected number never
  leaves the machine.
- **Citizen text is never written to the logs.** Logs record how long something
  took and which step it was, not what a citizen said. Every finished log line is
  scrubbed of identifiers before it is written, so a future change cannot leak
  one by accident.
- **For a departmental rollout**, the AI can run entirely on a machine inside the
  department, with nothing leaving the boundary. This is a configuration change,
  not a rebuild.
- **The status page states the truth about this** at any moment: whether an
  outside service is in use, and whether audio and text are leaving the machine.

Speech recognition, when switched on, does send audio to a service outside the
department. That is stated on the status page rather than left implicit, and it
can be pointed at a departmental engine instead.

---

## What is recorded for each petition

- The details as the citizen gave them, and the checked values.
- Any correction made during the conversation: which detail, from what, to what.
- Whether each detail was typed, spoken, or inferred from speech.
- A stable reference number, printed on the document. The same session always
  produces the same reference, so a reprint matches the citizen's copy.
- The result of the final check on the generated file.

---

## Current scope

One form: a general petition to the District Collectorate. Adding a second form —
an income certificate, a residence certificate — is a configuration file, not
development work. Adding a question to the existing form is four lines in that
file.

**Not included, and deliberately separate:** advising on scheme eligibility,
identifying the Act or the department with jurisdiction, and checking case status
on a government portal. Each of these needs its own source of authority and fails
in its own way, so each belongs in its own component rather than folded into the
conversation. The system is built with defined attachment points for them.

---

## Status

Working end to end in Tamil and English, with 239 automated tests covering the
checks on official values, whole conversations in both languages, corrections,
interruption and recovery, Aadhaar containment, and the contents of the generated
document.

The generated Tamil PDF has been checked by eye, not only by confirming that a
file was produced: Tamil vowel signs reorder around the consonant they attach to,
and a converter without proper shaping produces a file of the right size that is
unreadable on the page.

Setup and operation: [backend/README.md](backend/README.md).
