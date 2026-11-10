import hashlib
import re
import subprocess
import pyotp
import time
import os
import shlex
import shutil
import sys
from datetime import datetime

from timo import fileio, ui
from timo import messages as msg


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


BACKUP_PREFIX = "secrets.enc.bak."
PREVIEW_WINDOWS = 20  # codes handed to the fzf preview: 20 x 30s = 10 minutes


def secret_key(secret):
    """A secret in one canonical form, so "jbsw y3dp" and "JBSWY3DP==" compare equal."""
    return re.sub(r"[\s=-]", "", str(secret)).upper()


def now_stamp():
    """The current local time for "date_added", e.g. "2026-11-05T16:02:11+01:00"."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def merge_accounts(existing, new_accounts):
    """Append new accounts, skipping any whose secret is already present.

    Only the secret counts: the same key under another label (renamed with
    --edit, or exported differently) is the same account.
    Returns (merged, added_count).
    """
    seen = {secret_key(a.get("secret", "")) for a in existing}
    merged = list(existing)
    added = 0
    for acc in new_accounts:
        key = secret_key(acc["secret"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(acc)
        added += 1
    return merged, added


def preview_codes(indexed_accounts, now, windows=PREVIEW_WINDOWS):
    """Codes for the next few 30s windows, so the fzf preview never sees a secret.

    Returns {"start": t0, "interval": 30, "codes": {"<index>": [code, ...]}}.
    """
    interval = 30
    start = int(now) // interval * interval
    codes = {}
    for i, acc in indexed_accounts:
        totp = make_totp(acc)
        codes[str(i)] = [totp.at(start + k * interval) for k in range(windows)]
    return {"start": start, "interval": interval, "codes": codes}


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


def create_backup(src_path, backup_dir):
    """Write a private copy of src_path into backup_dir; never overwrites a backup."""
    with open(src_path, "rb") as f:
        data = f.read()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    name = f"{BACKUP_PREFIX}{timestamp}"
    n = 0
    while True:
        backup_path = os.path.join(backup_dir, name if n == 0 else f"{name}_{n}")
        try:
            fileio.write_new_private(backup_path, data)
            return backup_path
        except FileExistsError:  # a backup was made in the same second
            n += 1


def list_backups(backup_dir):
    if not os.path.isdir(backup_dir):
        return []
    return sorted(
        f for f in os.listdir(backup_dir)
        if f.startswith(BACKUP_PREFIX)
    )


def backup_time(backup_dir, name):
    """When a backup was made: from its name, or the file's mtime if the name has no date."""
    stamp = name[len(BACKUP_PREFIX):len(BACKUP_PREFIX) + 19]
    try:
        return datetime.strptime(stamp, "%Y-%m-%d_%H-%M-%S").timestamp()
    except ValueError:
        return os.path.getmtime(os.path.join(backup_dir, name))


def fzf_args(python_path, preview_script, prompt="Select OTP: "):
    """fzf command for lines of the form "<index>\t<label>".

    --with-nth hides the index from display and search (fzf matches only the
    shown text), but fzf still prints the whole line, index included.
    Don't add --nth: with --with-nth, recent fzf applies it to the shown
    text, so --nth=2.. would match nothing.
    """
    return [
        "fzf",
        f"--prompt={prompt}",
        "--delimiter=\t",
        "--with-nth=2..",
        # fzf runs this through $SHELL, so quote the paths: pipx puts Python
        # under "~/Library/Application Support" on macOS.
        "--preview", f"{shlex.quote(python_path)} {shlex.quote(preview_script)} {{1}}",
        "--preview-window=down:1:wrap",
    ]


def scan_qr_image(seen=()):
    """Read a QR code from an image path, or from the webcam if the path is left empty.

    The webcam skips QR codes in seen (the parts of an export already read) and
    anything that isn't an otpauth link. Returns the text, or None.
    """
    path = os.path.expanduser(input(msg.PROMPT_QR_PATH).strip())
    if not path:
        return scan_qr_webcam(seen)
    if not os.path.exists(path):
        ui.error(msg.QR_NOT_FOUND.format(path=path))
        return None
    if not os.path.isfile(path):
        ui.error(msg.QR_NOT_A_FILE.format(path=path))
        return None
    if not os.access(path, os.R_OK):
        ui.error(msg.QR_NOT_READABLE.format(path=path))
        return None
    if not shutil.which("zbarimg"):
        ui.error(msg.NO_ZBARIMG, msg.NO_ZBARIMG_HINT)
        return None
    ui.note(msg.SCANNING_QR)
    try:
        result = subprocess.run(
            ["zbarimg", "--raw", "--quiet", path],
            check=True, capture_output=True, text=True
        )
    except FileNotFoundError:
        ui.error(msg.NO_ZBARIMG, msg.NO_ZBARIMG_HINT)
        return None
    except subprocess.CalledProcessError:
        ui.error(msg.QR_UNREADABLE.format(path=path))
        return None
    return result.stdout.strip()


def scan_qr_webcam(seen=()):
    from timo import webcam

    ui.note(msg.SCANNING_WEBCAM)
    try:
        return webcam.scan(lambda text: text.lower().startswith("otpauth") and text not in seen)
    except webcam.Unavailable as e:
        ui.error(e.message, *e.hints)
        return None


def read_hidden(prompt):
    """Read one line without echoing it, with no length limit.

    getpass() reads in canonical mode, which macOS caps at 1024 bytes per
    line, enough to silently truncate a large migration string. This turns
    off echo and canonical mode instead and reads byte by byte.
    """
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip("\r\n")

    import termios

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    new = termios.tcgetattr(fd)
    new[3] &= ~(termios.ECHO | termios.ICANON)
    new[6][termios.VMIN] = 1
    new[6][termios.VTIME] = 0

    chars = []
    try:
        termios.tcsetattr(fd, termios.TCSAFLUSH, new)
        sys.stdout.write(prompt)
        sys.stdout.flush()
        while True:
            ch = os.read(fd, 1)
            if ch in (b"\n", b"\r"):
                break
            if ch == b"" or (ch == b"\x04" and not chars):
                raise EOFError
            if ch in (b"\x7f", b"\x08"):
                if chars:
                    chars.pop()
                continue
            chars.append(ch)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\n")
        sys.stdout.flush()
    return b"".join(chars).decode("utf-8", errors="replace")
