"""Create a demo vault with fake accounts and random secrets.

Usage: python seed.py TIMO_HOME PASSPHRASE
"""
import os
import sys
from datetime import datetime, timezone

import pyotp

from timo.vault import Vault

ACCOUNTS = [
    ("GitHub", "you@example.com"),
    ("Google", "you@gmail.com"),
    ("AWS", "root"),
    ("Bitwarden", "you@example.com"),
    ("Cloudflare", "you@example.com"),
    ("Discord", "you#0001"),
]

home, passphrase = sys.argv[1], sys.argv[2]
now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
accounts = [
    dict(issuer=issuer, name=name, secret=pyotp.random_base32(), algorithm="SHA1", digits=6, date_added=now)
    for issuer, name in ACCOUNTS
]
os.makedirs(home, mode=0o700, exist_ok=True)
Vault(os.path.join(home, "secrets.enc"), passphrase).save(accounts)
