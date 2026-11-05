"""Single accounts: otpauth:// links and plain secret keys.

An otpauth:// link is what a site's 2FA setup QR code holds, e.g.
otpauth://totp/GitHub:me@example.com?secret=JBSW...&issuer=GitHub
(format: https://github.com/google/google-authenticator/wiki/Key-Uri-Format).
"""
import base64
import binascii
import re
from urllib.parse import parse_qsl, unquote, urlsplit

PERIOD = 30  # the only code lifetime otpcli supports
BASE32 = re.compile(r"[A-Z2-7]+")


def normalize_secret(text):
    """Turn a key as sites show it ("jbsw y3dp ehpk 3pxp") into bare base32."""
    secret = re.sub(r"[\s-]", "", text).rstrip("=").upper()
    if not secret:
        raise ValueError("No secret key given")
    if not BASE32.fullmatch(secret):
        raise ValueError("That doesn't look like a secret key (expected letters A-Z and digits 2-7)")
    try:
        base64.b32decode(secret + "=" * (-len(secret) % 8))
    except binascii.Error:
        raise ValueError("That doesn't look like a secret key (wrong length)") from None
    return secret


def parse_otpauth_uri(uri):
    """Decode an otpauth:// link into an account dict.

    "issuer" or "name" may come back empty when the link doesn't say.
    """
    parts = urlsplit(uri.strip())
    if parts.scheme.lower() != "otpauth":
        raise ValueError("Not an otpauth:// link")
    kind = parts.netloc.lower()
    if kind == "hotp":
        raise ValueError("Counter-based (HOTP) accounts aren't supported")
    if kind != "totp":
        raise ValueError(f"Unknown code type {kind!r} in the link (expected totp)")

    label = unquote(parts.path.lstrip("/"))
    label_issuer, sep, name = label.partition(":")
    if not sep:
        label_issuer, name = "", label
    params = {key.lower(): value for key, value in parse_qsl(parts.query)}

    if "secret" not in params:
        raise ValueError("The link has no secret key")
    try:
        digits = int(params.get("digits", 6))
    except ValueError:
        raise ValueError(f"Unsupported digits {params['digits']!r} (use 6 or 8)") from None
    period = params.get("period", str(PERIOD))
    if period != str(PERIOD):
        raise ValueError(f"Only {PERIOD}-second codes are supported (this link uses {period})")

    return {
        "issuer": (params.get("issuer") or label_issuer).strip(),
        "name": name.strip(),
        "secret": normalize_secret(params["secret"]),
        "algorithm": params.get("algorithm", "SHA1").upper(),
        "digits": digits,
    }
