import hashlib
import subprocess
import pyotp
import time
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from collections import Counter


def load_accounts(json_path):
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            return json.load(f)


def save_accounts(accounts, json_path):
    with open(json_path, "w") as f:
        json.dump(accounts, f, indent=2)


DIGESTS = {
    "SHA1": hashlib.sha1,
    "SHA256": hashlib.sha256,
    "SHA512": hashlib.sha512,
    "MD5": hashlib.md5,
}


def make_totp(account):
    """Build a TOTP generator from an account dict.

    "algorithm" and "digits" are optional; files written before they were
    stored default to SHA1 and 6 digits.
    """
    algorithm = str(account.get("algorithm", "SHA1")).upper()
    if algorithm not in DIGESTS:
        raise ValueError(f"Unsupported algorithm {algorithm!r} (use one of: {', '.join(DIGESTS)})")
    digits = account.get("digits", 6)
    if digits not in (6, 8):
        raise ValueError(f"Unsupported digits {digits!r} (use 6 or 8)")
    return pyotp.TOTP(account["secret"], digits=digits, digest=DIGESTS[algorithm])


def generate_otp(account):
    totp = make_totp(account)
    return totp.now(), totp.interval - int(time.time()) % totp.interval


BACKUP_PREFIX = "secrets.json.bak."


def save_accounts_secure(accounts, json_path):
    """Write accounts atomically with 0600 permissions (root-owned when run as root)."""
    directory = os.path.dirname(os.path.abspath(json_path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".secrets.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(accounts, f, indent=2)
        os.chmod(tmp_path, 0o600)
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            os.chown(tmp_path, 0, 0)
        os.replace(tmp_path, json_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def import_accounts(new_accounts, json_path, backup_dir):
    """Merge new_accounts into the secrets file, backing it up first.

    Accounts already present (same issuer, name and secret) are skipped.
    Returns the number of accounts added.
    """
    existing = load_accounts(json_path) or []
    if os.path.exists(json_path):
        create_backup(json_path, backup_dir)

    seen = {(a.get("issuer"), a.get("name"), a.get("secret")) for a in existing}
    merged = list(existing)
    added = 0
    for acc in new_accounts:
        key = (acc["issuer"], acc["name"], acc["secret"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(acc)
        added += 1

    save_accounts_secure(merged, json_path)
    return added


def resolve_backup_path(backup_dir, backup_name):
    """Return the absolute path of a backup, refusing anything outside backup_dir."""
    if (
        not backup_name
        or os.path.basename(backup_name) != backup_name
        or not backup_name.startswith(BACKUP_PREFIX)
    ):
        raise ValueError(f"Invalid backup name: {backup_name!r}")

    root = os.path.realpath(backup_dir)
    full_path = os.path.realpath(os.path.join(root, backup_name))
    if os.path.dirname(full_path) != root:
        raise ValueError(f"Invalid backup name: {backup_name!r}")
    return full_path


def create_backup(json_path, backup_dir):
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_name = f"{BACKUP_PREFIX}{timestamp}"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(json_path, backup_path)
    return backup_path


def list_backups(backup_dir):
    if not os.path.isdir(backup_dir):
        return []
    return sorted(
        f for f in os.listdir(backup_dir)
        if f.startswith(BACKUP_PREFIX)
    )


def restore_backup(backup_name, backup_dir, json_path):
    full_path = resolve_backup_path(backup_dir, backup_name)
    shutil.copy2(full_path, json_path)
    return full_path


def get_stats(accounts):
    total = len(accounts)
    issuers = [acc.get("issuer", "Unknown") for acc in accounts]
    issuer_counts = Counter(issuers)
    return total, issuer_counts


def _scan_qr_image():
    path = input("Path to QR code image (e.g. /home/user/Downloads/otp.png): ").strip()
    if not os.path.exists(path):
        print("File not found. Please check the path and try again.")
        return None
    if not os.path.isfile(path):
        print("Path is not a file. Please provide a valid file path.")
        return None
    if not os.access(path, os.R_OK):
        print("File is not readable. Please check permissions.")
        return None
    if not shutil.which("zbarimg"):
        print("zbarimg is not installed. Please install it first.")
        return None
    print("Scanning QR code...")
    try:
        result = subprocess.run(
            ["zbarimg", "--raw", "--quiet", path],
            check=True, capture_output=True, text=True
        )
    except FileNotFoundError:
        print("'zbarimg' not found. Please install it first.")
        return None
    except subprocess.CalledProcessError:
        print("Failed to read QR code using zbarimg.")
        return None
    return result.stdout.strip()


def _read_migration_uri(use_qr):
    if use_qr:
        return _scan_qr_image()
    return input("Paste otpauth-migration string: ").strip()


def initialize_otp_setup(json_path, backup_dir):
    from utils.protobuf.extract_google_otp_from_qr import parse_migration_uri

    if hasattr(os, "geteuid") and os.geteuid() != 0:
        print("This command must be run as root (use sudo).")
        sys.exit(1)

    choice = input("Do you already have the OTP migration string? [y/N] ").strip().lower()
    use_qr = choice != "y"

    collected = []
    while True:
        uri = _read_migration_uri(use_qr)
        if not uri:
            break
        try:
            accounts, skipped, batch_index, batch_size = parse_migration_uri(uri)
        except ValueError as e:
            print(f"Error: {e}")
            break

        collected.extend(accounts)
        print(f"\nFound {len(accounts)} account(s) (QR {batch_index + 1} of {batch_size}):")
        for acc in accounts:
            print(f"  {acc['issuer']} ({acc['name']})")
        for label in skipped:
            print(f"  Skipped {label}: counter-based (HOTP) accounts are not supported.")

        if batch_index + 1 >= batch_size:
            break
        more = input(f"\nThe export has {batch_size} QR codes. Import the next one? [Y/n] ").strip().lower()
        if more == "n":
            break

    if not collected:
        print("Nothing imported.")
        return

    had_file = os.path.exists(json_path)
    added = import_accounts(collected, json_path, backup_dir)
    skipped = len(collected) - added
    if had_file:
        print("\nExisting secrets backed up before import.")
    print(f"Imported {added} new account(s)" + (f", skipped {skipped} already present." if skipped else "."))
