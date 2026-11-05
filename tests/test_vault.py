import json
import os

import pytest

from totp_cli import vault
from totp_cli.vault import Vault, WrongPassphrase, VaultFormatError, decrypt, encrypt


@pytest.fixture(autouse=True)
def fast_scrypt(monkeypatch):
    monkeypatch.setattr(vault, "SCRYPT_N", 2**10)


ACCOUNTS = [{"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP"}]


def test_roundtrip():
    assert decrypt(encrypt(ACCOUNTS, "correct horse"), "correct horse") == ACCOUNTS


def test_wrong_passphrase():
    with pytest.raises(WrongPassphrase):
        decrypt(encrypt(ACCOUNTS, "correct horse"), "wrong")


def test_ciphertext_does_not_contain_secrets():
    blob = encrypt(ACCOUNTS, "correct horse")
    assert b"JBSWY3DPEHPK3PXP" not in blob
    assert b"GitHub" not in blob


def test_each_encryption_uses_fresh_salt_and_nonce():
    a = json.loads(encrypt(ACCOUNTS, "pw"))
    b = json.loads(encrypt(ACCOUNTS, "pw"))
    assert a["salt"] != b["salt"]
    assert a["nonce"] != b["nonce"]


def test_tampered_ciphertext_is_rejected():
    envelope = json.loads(encrypt(ACCOUNTS, "pw"))
    envelope["ciphertext"] = envelope["ciphertext"][:-4] + ("AAAA" if not envelope["ciphertext"].endswith("AAAA") else "BBBB")
    with pytest.raises(WrongPassphrase):
        decrypt(json.dumps(envelope).encode(), "pw")


@pytest.mark.parametrize("blob", [b"", b"not json", b'{"version": 99}', b"[]"])
def test_bad_format(blob):
    with pytest.raises(VaultFormatError):
        decrypt(blob, "pw")


def test_vault_save_and_load(tmp_path):
    path = tmp_path / "cfg" / "secrets.enc"
    Vault(str(path), "pw").save(ACCOUNTS)

    assert Vault(str(path), "pw").load() == ACCOUNTS
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert os.stat(path.parent).st_mode & 0o777 == 0o700
    assert [p.name for p in path.parent.iterdir()] == ["secrets.enc"]  # no temp files left


def test_vault_load_wrong_passphrase(tmp_path):
    path = tmp_path / "secrets.enc"
    Vault(str(path), "pw").save(ACCOUNTS)
    with pytest.raises(WrongPassphrase):
        Vault(str(path), "nope").load()
