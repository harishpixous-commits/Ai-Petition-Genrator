"""Provision an office-wide review account; passwords never enter argv.

Two ways in, and the password reaches neither the command line nor the
shell's history in either:

    interactive   prompted twice, hidden. What a person at a terminal uses.
    OFFICER_PASSWORD in the environment   for automation. What the
                  `Create Officer Account` workflow uses, so the value can
                  come from a GitHub secret and never be printed.

Re-running for an existing username RESETS that account and revokes its
sessions. That is the supported way to change a password.

THE ACCOUNT LIVES WHERE THE DATABASE LIVES. On a server that is the Docker
volume, not this repository and not a laptop — so an account created locally
does not work against the deployed site, and the other way round.
"""

import argparse
import os
import sys
from getpass import getpass
from pathlib import Path

# `backend/` on the path, the way every other script here does it.
#
# `python -m scripts.create_officer` already worked, because -m puts the
# working directory on the path — that is the documented invocation and it
# was fine. `python scripts/create_officer.py` did not, because running a
# file puts only its OWN directory there. Both work now, which matters
# because the deployment workflow runs the file form inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.officer_store import database, provision  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("username")
parser.add_argument("--name", required=True)
args = parser.parse_args()

password = os.environ.get("OFFICER_PASSWORD")
if password:
    print("Using the password from OFFICER_PASSWORD.")
else:
    password = getpass("Password (at least 12 characters): ")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords do not match.")

username = args.username.strip().casefold()
with database() as db:
    existed = db.execute(
        "SELECT 1 FROM officers WHERE username=?", (username,)
    ).fetchone() is not None
    first = db.execute("SELECT COUNT(*) c FROM officers").fetchone()["c"] == 0

try:
    provision(username, args.name.strip(), password)
except ValueError as problem:
    raise SystemExit(str(problem)) from None

print(f"{'Reset' if existed else 'Created'} officer '{username}' ({args.name.strip()}).")
print("Previous sessions for this account were revoked.")

if first:
    # Worth saying once, loudly: this is the switch, not a side effect of it.
    print()
    print("This was the FIRST officer account, so OFFICE MODE is now on.")
    print("A citizen now sees only the petitions their own browser created;")
    print("everything else is reachable through the officer portal alone.")
    print("Nothing was deleted — the portal still shows all of them.")

sys.exit(0)
