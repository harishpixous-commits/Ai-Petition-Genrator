# Setting up a petition kiosk

Written for: the person installing a terminal in a government office.

A kiosk here is one machine standing in an office with a printer attached. A
citizen walks up, answers the questions on screen or by voice, and the
finished petition comes out of the printer. Nobody is asked to find a Print
button, nobody needs an account, and nobody has to get a file home.

## What you need

- Any PC or mini-PC that runs Google Chrome.
- A printer the machine can already print to. Set it as the **default**
  printer and print a test page from the operating system first — the browser
  sends to the default printer and cannot choose one for you.
- Network access to the petition service.

## Launching it

The petition prints **silently** only if Chrome is started with
`--kiosk-printing`. Without that flag the citizen is shown the ordinary print
dialog, which works but needs somebody to press Print.

Windows — make a shortcut with this target:

```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --kiosk-printing "https://ai-petition.pixoustech.app/#kiosk"
```

Linux:

```
google-chrome --kiosk --kiosk-printing "https://ai-petition.pixoustech.app/#kiosk"
```

What the two flags do:

- `--kiosk` fills the screen and removes the address bar, so the terminal
  cannot be navigated away from the petition.
- `--kiosk-printing` sends every print straight to the default printer with
  no dialog. **This is the one that matters.** It is a browser setting; a web
  page is not allowed to suppress the dialog on its own.

Put the shortcut in the machine's Startup folder so it comes back after a
power cut.

## Configuration

Set these on the server, not in the browser. All have safe defaults, and the
service works with none of them set.

| Setting | Default | What it does |
|---|---|---|
| `KIOSK_ENABLED` | `true` | Whether the Kiosk link appears at all. |
| `KIOSK_PRINT_MODE` | `dialog` | `dialog` or `silent`. See below — this one is a claim, not a switch. |
| `KIOSK_AUTO_PRINT` | `true` | Send the petition to the printer once it is ready and verified. |
| `KIOSK_PRINT_PACKAGE` | `petition_only` | `petition_only` or `combined`. Combined prints the enclosures too. |
| `KIOSK_IDLE_TIMEOUT_SECONDS` | `120` | How long to wait for somebody who has stopped answering before asking whether they are still there. |
| `KIOSK_RESET_AFTER_FINISH` | `true` | Clear the screen after the citizen finishes. |

### `KIOSK_PRINT_MODE` is a statement about the machine

It does not make printing silent. Nothing a web page does can. It tells the
page **which thing is about to happen**, so that the screen describes it
accurately:

- `dialog` — the citizen is told the print window is open and to press
  Print. True on any ordinary browser.
- `silent` — the citizen is told the petition has been **sent to the
  printer**. Only set this on a terminal launched with `--kiosk-printing` or
  an equivalent managed print path, where the dialog genuinely does not
  appear.

Setting `silent` on a machine that still shows a dialog changes nothing
except what the screen claims, which is the one thing worth getting right.

Neither mode ever says "printed successfully". A browser cannot tell whether
paper came out of a printer, and a screen that claims it did sends a citizen
away from an empty tray.

## What the citizen sees

A welcome screen, then the same petition flow as the website — the same
questions, the same document, the same Tamil and English, the same voice.
Kiosk mode changes four things:

1. **Welcome screen.** "வணக்கம் / Welcome", one large button to begin.
2. **The petition prints by itself** once it is ready *and verified*. A
   document that failed verification is not put on paper. One document
   version prints once, however many times the screen updates; a second copy
   is something the citizen asks for.
3. **The screen clears afterwards**, with a visible countdown, so the next
   person in the queue does not see the last citizen's name, address and
   grievance. It also clears if somebody walks away mid-petition — asked
   first ("Are you still there?"), because thinking is not leaving.
4. **The ways off the page are hidden** — browsing saved petitions, the home
   page. The language switch stays, because it is the one control a kiosk
   must keep.

If the print fails, the petition stays on the screen with a **Try printing
again** button. It is never cleared because a printer was out of paper.

## Checking it works

1. Open the terminal and run one petition end to end with test details.
2. The printer should produce the letter with no dialog and no key press.
3. Wait 45 seconds without touching anything; the screen should return to a
   fresh first question.
4. Press the language selector and confirm the questions change to Tamil.

If the petition is ready but nothing prints, the cause is almost always one
of: the default printer is not set, the printer is out of paper, or Chrome
was launched without `--kiosk-printing`. Check them in that order.

## What this does not do

- It does not keep the petition on the machine. The record lives on the
  server, as it does for the website.
- It does not print a second copy. If one is needed, the Print button on the
  page is still there.
- It does not lock the machine down beyond the browser. Anything else — a
  guest account, disabled USB ports, an automatic nightly restart — is
  ordinary terminal hardening and belongs to whoever manages the site.
