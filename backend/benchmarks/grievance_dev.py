"""Development cases added while tuning. Look at these as often as you like.

WHAT SEPARATES THIS FILE FROM `grievance_heldout.py` is not the content, it is
the permission. These may be read, failed against, and used to justify a change
to the taxonomy or the matcher. The held-out set may not.

WHY THESE CASES EXIST. Scoring the held-out set for the first time showed two
structural gaps that `grievance_cases.py` could not have caught, because it
contained no example of either:

  OTHER WAS DEAD. The category is in `CATEGORIES`, the officer portal can
  display it, and NO code path ever returned it — so a genuine grievance about
  something outside the ten known subjects could only ever come back UNKNOWN.
  The original set had not one OTHER case, so nothing failed.

  INDIRECT PHRASING. Real complaints often name the consequence and leave the
  subject implied: "my children cannot study after dark" is a street light
  complaint that contains no lighting word at all. The original set was
  written subject-first and never tested this.

Both are added here so that any fix is justified by a set it is allowed to be
justified by. The held-out number is reported separately, and the report says
plainly which measurement came before these changes and which after.

EVERYTHING IS INVENTED. No citizen text, no real names, no real addresses.
"""

from __future__ import annotations

from .grievance_cases import Case

# --------------------------------------------------------------------------- #
# A real grievance that none of the ten subjects covers
# --------------------------------------------------------------------------- #
#
# The distinction that matters is between "this says nothing" and "this says
# something I have no category for". Both used to come back UNKNOWN, which
# told an officer the same thing about two very different petitions.

OTHER_CASES: tuple[Case, ...] = (
    Case("There are stray dogs in our street and two children have been "
         "bitten this month, but nobody has come to catch them.",
         "en", "OTHER", "a real grievance, no category covers it"),
    Case("The government hospital in our town has had no doctor on duty at "
         "night for three weeks.", "en", "OTHER"),
    Case("The bus that used to run to our village at six in the morning has "
         "been stopped and the schoolchildren cannot reach the school.",
         "en", "OTHER"),
    Case("Our burial ground has been fenced off by a private party and "
         "funerals are being obstructed.", "en", "OTHER"),
    Case("The anganwadi centre has had no supply of nutritional food for the "
         "children since last month.", "en", "OTHER"),
    Case("A mobile tower has been put up next to the primary school without "
         "any consultation and residents object.", "en", "OTHER"),
    Case("தெருநாய்கள் தொல்லை அதிகமாக உள்ளது, யாரும் நடவடிக்கை எடுக்கவில்லை.",
         "ta", "OTHER"),
    Case("அரசு மருத்துவமனையில் இரவு நேரத்தில் மருத்துவர் இல்லை.",
         "ta", "OTHER"),
    Case("സർക്കാർ ആശുപത്രിയിൽ രാത്രി ഡോക്ടർ ഇല്ല.", "ml", "OTHER"),
    Case("మా ఊరికి వచ్చే బస్సు ఆపేశారు, పిల్లలు బడికి వెళ్లలేకపోతున్నారు.",
         "te", "OTHER"),
    Case("सरकारी अस्पताल में रात को कोई डॉक्टर नहीं रहता।", "hi", "OTHER"),
)

# --------------------------------------------------------------------------- #
# Nothing to classify — the other side of the same distinction
# --------------------------------------------------------------------------- #
#
# These must NOT become OTHER. A petition that names no subject needs a human
# to ask the citizen what it is about, and filing it as "other" hides that.

STILL_UNKNOWN: tuple[Case, ...] = (
    Case("Sir, I request you to kindly do the needful at the earliest.",
         "en", "UNKNOWN", "a request with no subject"),
    Case("I have come to this office many times and nobody listens to me.",
         "en", "UNKNOWN", "distress, no subject"),
    Case("Please consider my application favourably and oblige.",
         "en", "UNKNOWN"),
    Case("Respected sir, kindly help me, I am a poor person and have nobody "
         "to speak for me in this matter.", "en", "UNKNOWN",
         "long, emotional, and still names nothing"),
    Case("ஐயா, தயவுசெய்து உதவி செய்யுங்கள், நான் ஏழை.", "ta", "UNKNOWN"),
    Case("സർ, ദയവായി സഹായിക്കണം.", "ml", "UNKNOWN"),
    Case("సార్, దయచేసి సహాయం చేయండి.", "te", "UNKNOWN"),
    Case("सर, कृपया मेरी मदद करें।", "hi", "UNKNOWN"),
)

# --------------------------------------------------------------------------- #
# The subject stated only by its consequence
# --------------------------------------------------------------------------- #

INDIRECT: tuple[Case, ...] = (
    Case("My children cannot study after seven because the lane is "
         "completely dark.", "en", "STREET_LIGHT", "no lighting word"),
    Case("The women in our street are walking to the next ward with pots "
         "every morning.", "en", "WATER", "no water word except pots"),
    Case("Autos refuse to come down our lane after the rains broke up the "
         "surface.", "en", "ROAD"),
    Case("We cannot open the windows on that side of the house because of "
         "the smell from the open channel.", "en", "SANITATION"),
    Case("The amount that used to be credited to my account every month "
         "stopped coming after my husband died.", "en", "PENSION"),
    Case("எனது குழந்தைகள் இரவில் படிக்க முடியவில்லை, தெரு இருட்டாக உள்ளது.",
         "ta", "STREET_LIGHT"),
    Case("കുട്ടികൾക്ക് വൈകുന്നേരം പഠിക്കാൻ കഴിയുന്നില്ല, വഴി ഇരുട്ടാണ്.",
         "ml", "STREET_LIGHT"),
)

EXTRA: tuple[Case, ...] = OTHER_CASES + STILL_UNKNOWN + INDIRECT
