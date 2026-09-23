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

## What the citizen sees

The same petition flow as the website — the same questions, the same
document, the same Tamil and English, the same voice. Kiosk mode changes
three things:

1. The petition prints by itself the moment it is ready.
2. A green panel then says it has printed, and **clears the screen after 45
   seconds** so the next person in the queue does not see the last citizen's
   name, address and grievance. There is an "I need more time" button for
   somebody still reading.
3. The links that lead away from the task — browsing saved petitions, the
   home page — are hidden. The language switch stays, because it is the one
   control a kiosk must keep.

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
