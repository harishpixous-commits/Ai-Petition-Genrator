"""Labelled queries for measuring retrieval on the real Tamil Nadu corpus.

WHAT THIS MEASURES. Retrieval, on its own — whether the right government
document comes back for a question — separately from anything a model then
writes. A generator can only cite what retrieval handed it, so a retrieval
failure surfaces later as a missing or wrong citation and gets blamed on the
wrong stage unless it is measured here first.

WHY THE LABELS ARE DEFENSIBLE. Each target is a narrow official instrument
whose subject was verified when it was acquired: G.O. Ms. No. 104 of 2025 is
about same-day self-certified licences for small shops and nothing else; G.O.
Ms. No. 106 of 2014 is about septage. A query is labelled with the documents
that GOVERN its subject, by manifest id. Where several legitimately do — the
2023 Rules and the amendment that changed them — all are listed, and any one
of them in the top k counts as a hit.

WHAT IS DELIBERATELY NOT DONE. No retrieval parameter is tuned against these
cases. They are an evaluation set. A change made to raise this number must be
justified on other grounds and then measured here, or the number stops meaning
anything.

THE CROSS-LANGUAGE CASES are the point. The corpus is mostly English and a
citizen writes in Tamil, Malayalam, Telugu or Hindi. The same five intents are
asked in every language, with the same gold documents, so the per-language
numbers are directly comparable.

OUT-OF-CORPUS QUERIES are kept apart. Nothing in this corpus governs passport
renewal; retrieval will still return its nearest text, and what must happen
downstream is a refusal. They are reported separately and never counted as
misses.

Everything here was written for this purpose. No citizen text.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Query:
    text: str
    language: str
    expected: frozenset[str]
    intent: str


def q(text: str, language: str, intent: str, *expected: str) -> Query:
    return Query(text, language, frozenset(expected), intent)


# Gold documents per intent, by manifest id in corpus/tamil_nadu.yaml.
LICENCE_VALIDITY = ("tn-ulb-rules-2023", "tn-ulb-rules-amend-164-2026",
                    "tn-ulb-rules-2023-gazette")
SEPTAGE = ("tn-go-ms-106-2014-septage",)
WASTE = ("tn-swm-ready-reckoner", "tn-swm-rules-2016-tamil")
VILLAGE = ("tn-panchayats-act-1994",)
BUILDING = ("tn-combined-building-rules-2019", "tn-town-country-planning-act-1971")

ENGLISH: tuple[Query, ...] = (
    q("how long is a municipal trade licence valid before renewal", "en",
      "licence_validity", *LICENCE_VALIDITY),
    q("same day licence through self certification for a small shop", "en",
      "small_shop_licence", "tn-ulb-rules-amend-104-2025"),
    q("property tax assessment when the building is leased", "en",
      "property_tax", "tn-ulb-rules-amend-480-2025", "tn-ulb-rules-2023"),
    q("removal and treatment of septage from septic tanks", "en",
      "septage", *SEPTAGE),
    q("door to door collection of household garbage", "en", "waste", *WASTE),
    q("town panchayat reclassified as a municipality", "en",
      "reclassification", "tn-go-ms-208-2010-oddanchatram",
      "tn-district-municipalities-act-1920"),
    q("powers and duties of a village panchayat", "en", "village", *VILLAGE),
    q("permission to construct a building and approval of the plan", "en",
      "building", *BUILDING),
    q("fixing the seniority of municipal employees", "en",
      "seniority", "tn-ulb-rules-amend-162-2024"),
    q("status of a nominated member of a municipal council", "en",
      "nominated_member", "tn-ulb-amendment-act-30-2025", "tn-ulb-act-1998"),
)

TAMIL: tuple[Query, ...] = (
    q("வர்த்தக உரிமம் எத்தனை ஆண்டுகள் செல்லுபடியாகும்", "ta",
      "licence_validity", *LICENCE_VALIDITY),
    q("செப்டிக் டேங்க் கழிவுகளை அகற்றுதல்", "ta", "septage", *SEPTAGE),
    q("வீடு வீடாக குப்பை சேகரிப்பு", "ta", "waste", *WASTE),
    q("கிராம ஊராட்சியின் அதிகாரங்களும் கடமைகளும்", "ta", "village", *VILLAGE),
    q("கட்டிட வரைபடத்திற்கு அனுமதி பெறுதல்", "ta", "building", *BUILDING),
)

MALAYALAM: tuple[Query, ...] = (
    q("ട്രേഡ് ലൈസൻസിന്റെ കാലാവധി എത്ര വർഷമാണ്", "ml",
      "licence_validity", *LICENCE_VALIDITY),
    q("സെപ്റ്റിക് ടാങ്കിലെ മാലിന്യം നീക്കം ചെയ്യൽ", "ml", "septage", *SEPTAGE),
    q("വീടുതോറുമുള്ള മാലിന്യ ശേഖരണം", "ml", "waste", *WASTE),
    q("ഗ്രാമ പഞ്ചായത്തിന്റെ അധികാരങ്ങളും ചുമതലകളും", "ml", "village", *VILLAGE),
    q("കെട്ടിട പ്ലാനിന് അനുമതി നേടൽ", "ml", "building", *BUILDING),
)

TELUGU: tuple[Query, ...] = (
    q("వ్యాపార లైసెన్సు ఎన్ని సంవత్సరాలు చెల్లుబాటు అవుతుంది", "te",
      "licence_validity", *LICENCE_VALIDITY),
    q("సెప్టిక్ ట్యాంక్ వ్యర్థాల తొలగింపు", "te", "septage", *SEPTAGE),
    q("ఇంటింటా చెత్త సేకరణ", "te", "waste", *WASTE),
    q("గ్రామ పంచాయతీ అధికారాలు మరియు విధులు", "te", "village", *VILLAGE),
    q("భవన ప్లాన్‌కు అనుమతి పొందడం", "te", "building", *BUILDING),
)

HINDI: tuple[Query, ...] = (
    q("व्यापार लाइसेंस कितने वर्षों के लिए वैध होता है", "hi",
      "licence_validity", *LICENCE_VALIDITY),
    q("सेप्टिक टैंक का कचरा हटाना", "hi", "septage", *SEPTAGE),
    q("घर-घर कचरा संग्रहण", "hi", "waste", *WASTE),
    q("ग्राम पंचायत के अधिकार और कर्तव्य", "hi", "village", *VILLAGE),
    q("भवन नक्शे की अनुमति प्राप्त करना", "hi", "building", *BUILDING),
)

#: Nothing in this corpus governs these. Reported apart; never a "miss".
OUT_OF_CORPUS: tuple[Query, ...] = (
    q("procedure to renew an Indian passport", "en", "none"),
    q("registration of a company for goods and services tax", "en", "none"),
    q("status of my income tax refund", "en", "none"),
)


def dataset() -> tuple[Query, ...]:
    return ENGLISH + TAMIL + MALAYALAM + TELUGU + HINDI
