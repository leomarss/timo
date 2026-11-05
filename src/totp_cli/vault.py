"""Encrypted storage for TOTP accounts.

The secrets file is a small JSON envelope: the accounts list is encrypted with
AES-256-GCM, using a key derived from the user's passphrase with scrypt. Each
save uses a fresh random salt and nonce. Nothing in the envelope reveals the
accounts; a wrong passphrase and a tampered file both fail authentication.
"""
import base64
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from totp_cli import fileio

FORMAT_VERSION = 1
SCRYPT_N = 2**17  # about 0.2s per unlock on a modern laptop
SCRYPT_R = 8
SCRYPT_P = 1
AAD = b"totp-cli secrets v1"


class WrongPassphrase(Exception):
    pass


class VaultFormatError(Exception):
    pass


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def _derive(passphrase, salt, n, r, p):
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(passphrase.encode("utf-8"))


def encrypt(accounts, passphrase):
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive(passphrase, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    plaintext = json.dumps(accounts).encode("utf-8")
    envelope = {
        "version": FORMAT_VERSION,
        "kdf": {"name": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P},
        "salt": _b64(salt),
        "nonce": _b64(nonce),
        "ciphertext": _b64(AESGCM(key).encrypt(nonce, plaintext, AAD)),
    }
    return json.dumps(envelope, indent=2).encode("utf-8")


def decrypt(blob, passphrase):
    try:
        envelope = json.loads(blob)
        if not isinstance(envelope, dict) or envelope.get("version") != FORMAT_VERSION:
            raise VaultFormatError("Unsupported secrets file version.")
        kdf = envelope["kdf"]
        if kdf.get("name") != "scrypt":
            raise VaultFormatError("Unsupported key derivation.")
        salt = base64.b64decode(envelope["salt"])
        nonce = base64.b64decode(envelope["nonce"])
        ciphertext = base64.b64decode(envelope["ciphertext"])
        n, r, p = int(kdf["n"]), int(kdf["r"]), int(kdf["p"])
    except VaultFormatError:
        raise
    except (ValueError, KeyError, TypeError) as e:
        raise VaultFormatError(f"Not a totp-cli secrets file: {e}") from e

    key = _derive(passphrase, salt, n, r, p)
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, AAD)
    except InvalidTag:
        raise WrongPassphrase("Wrong passphrase (or the file was modified).") from None
    return json.loads(plaintext)


class Vault:
    def __init__(self, path, passphrase):
        self.path = path
        self.passphrase = passphrase

    def exists(self):
        return os.path.exists(self.path)

    def load(self):
        with open(self.path, "rb") as f:
            return decrypt(f.read(), self.passphrase)

    def save(self, accounts):
        fileio.write_private(self.path, encrypt(accounts, self.passphrase))
