"""Provision an office-wide review account locally; passwords never enter argv."""

import argparse
from getpass import getpass

from app.services.officer_store import provision

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("username")
p.add_argument("--name", required=True)
a = p.parse_args()
password = getpass("Password (at least 12 characters): ")
if password != getpass("Confirm password: "):
    raise SystemExit("Passwords do not match.")
provision(a.username, a.name, password)
print("Officer account saved. Previous sessions for this account were revoked.")
