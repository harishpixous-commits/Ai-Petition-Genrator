# Loading government documents into the petition assistant

Written for: the department that owns the documents, and whoever runs the
service for them.

## What this is about

The petition assistant can show an officer which Act, which Rules and which
Government Order apply to a grievance, with a citation on every line. That
feature is built, tested and switched on. It has no documents.

An empty corpus is not a fault — the panel stays silent rather than inventing
anything, and every petition is produced exactly as before. But until documents
are loaded, the panel is silent for every petition.

**This is a content task, not a development task.** What follows is the
procedure, what was verified on real documents, and the two things that still
need a decision from the department.

## What was verified, on real documents

On 9 October 2026 two genuine Government Orders were downloaded from
`www.tn.gov.in` and run through the pipeline end to end:

- **G.O.(Ms) No.208, 02.09.2010** — Oddanchatram Town Panchayat reclassified as
  a Second Grade Municipality
- **G.O.(Ms) No.106, 01.09.2014** — Septage Management operative guidelines

Both downloaded without a login or a captcha, both were read correctly, and
both produced sensible chunks. The first is a *local body* document — it says
which body covers a place — which is the kind the `local_body_directory`
document type and the `jurisdiction` finding exist for.

Two real defects were found by doing this, and both are fixed:

1. **The issuing department was read off the wrong line.** Every Government
   Order opens by citing earlier orders, and the first department named is
   therefore almost never the issuing one. G.O. 208 was being attributed to the
   "Supply (Election) Department" and dated 14.07.2006 — both belonging to a
   2006 order it cites. It now reads the header.

2. **A scanned header did not match at all.** The real line is
   `Municipal Administration &Water Supply (M.A.5)Department` — no space before
   "Department", and a digit inside the section code. The pattern required a
   space and allowed no digits, so the issuing office was invisible.

Where the issuing date cannot be read — on G.O. 208 the scan rendered it
`Dated:O~.09.2010`, which is not a date — **the field is left empty rather than
filled from a cited order.** An officer who sees no date goes and checks; an
officer who sees 2006 on a 2010 order has no reason to.

## The procedure

Run from `backend/`. The order matters and is worth following the first few
times.

```
python scripts/ingest.py inspect <file-or-url>     # read it, index nothing
python scripts/ingest.py preview <file-or-url>     # read the chunks it makes
python scripts/ingest.py add     <file-or-url> --official --provenance "..."
python scripts/ingest.py show    <document-id>     # confirm what went in
python scripts/ingest.py status
```

`inspect` is not a formality. It prints the department, the Act, the G.O.
number and the date that the pipeline read off the document, and **those are
read from a scan and can be wrong**. Correct them on the `add` command rather
than accepting them.

A folder works as well as a file, and re-running `add` does nothing unless the
file has changed — so this can be put on a schedule against a folder the
department syncs into.

### Authority has to be earned

A document is marked `official` or `departmental` only when whoever ran the
command said so **and** recorded where the copy came from — `--provenance`, a
source URL, or a G.O. number. Without that it is indexed as `unknown`: still
searchable, still cited, but it no longer outranks anything and can never make
a document mandatory for a citizen.

Nothing is inferred from a filename. This is deliberate: the whole value of the
panel is that an officer can trust it, and a corpus that promotes documents on
the strength of what they are called cannot be trusted.

### Where the documents are

Government Orders for Municipal Administration and Water Supply, and for the
Directorate of Town Panchayats, are published at:

```
https://www.tn.gov.in/dtp/gorders/        ~180 orders, 1981-2015, PDF and HTML
```

Direct document URLs follow the pattern
`https://www.tn.gov.in/dtp/gorders/maws_e_208_2010.pdf`, and `scripts/ingest.py`
accepts a URL directly.

**That list is not a recommendation of what to load.** Much of it is fund
releases and staff postings, which no citizen petition turns on, and the newest
entry is from 2015. Choosing the document set is the department's call.

## What still needs a decision from the department

**1. Which documents.** The ones that would change an officer's day are the
Acts and Rules a grievance is decided under, the standing procedural circulars,
and the current local body directory. Fund-release orders are noise. A
department officer can draw up that list in an afternoon; nobody outside the
department can draw it up at all.

**2. The local body directory.** The service can say which office a petition
belongs to — corporation, municipality, town panchayat or village panchayat —
but only from a document that says so. Tamil Nadu has something over twelve
thousand village panchayats, and **no list is shipped with this service on
purpose**: a list written from general knowledge would be wrong in ways nobody
could check, and a confident wrong answer about which office to visit is the
exact failure this layer exists to prevent. Ingest the department's own
directory with `--type local_body_directory` and every answer then carries a
citation back to it.

## What is deliberately not done

- **No citizen document ever enters this corpus.** Attachments a citizen
  uploads are kept apart, with tests enforcing the separation. The corpus is
  government reference material only.
- **Nothing is invented.** If no retrieved passage supports a finding, the
  finding is dropped rather than softened — strictly, for Acts, G.O. numbers
  and jurisdiction, which have to appear verbatim in a retrieved passage.
- **No bulk load was performed.** Two documents were ingested into a throwaway
  corpus to prove the pipeline against real material. The production corpus is
  untouched, because which documents go in is a decision for the department and
  not for whoever was testing the loader.
