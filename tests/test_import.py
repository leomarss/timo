import base64
import io
import os
import sys
from datetime import datetime
from urllib.parse import quote

import pytest

from totp_cli.protobuf import migration_pb2
from totp_cli.protobuf.migration import parse_migration_uri
from totp_cli.utils import list_backups, merge_accounts


def undated(accounts):
    """The accounts without date_added, after checking it's a valid timestamp."""
    for acc in accounts:
        datetime.fromisoformat(acc["date_added"])
    return [{k: v for k, v in acc.items() if k != "date_added"} for acc in accounts]


def make_uri(params, batch_index=0, batch_size=1):
    payload = migration_pb2.MigrationPayload()
    payload.version = 1
    payload.batch_index = batch_index
    payload.batch_size = batch_size
    for issuer, name, secret in params:
        p = payload.otp_parameters.add()
        p.secret = secret
        p.issuer = issuer
        p.name = name
    data = base64.b64encode(payload.SerializeToString()).decode()
    return f"otpauth-migration://offline?data={quote(data, safe='')}"


def b32(raw):
    return base64.b32encode(raw).decode().replace("=", "")


def test_parse_returns_accounts_and_batch_info():
    uri = make_uri([("GitHub", "me@x.com", b"0123456789")], batch_index=1, batch_size=3)
    accounts, skipped, batch_index, batch_size = parse_migration_uri(uri)
    assert accounts == [{"issuer": "GitHub", "name": "me@x.com", "secret": b32(b"0123456789"),
                         "algorithm": "SHA1", "digits": 6}]
    assert skipped == []
    assert (batch_index, batch_size) == (1, 3)


def test_parse_rejects_non_migration_uri():
    with pytest.raises(ValueError):
        parse_migration_uri("https://example.com/?data=abc")


def test_parse_rejects_missing_data():
    with pytest.raises(ValueError):
        parse_migration_uri("otpauth-migration://offline?foo=bar")


def run_import(cli, monkeypatch, *uris, answers=("y",)):
    """Run 'otpcli --initialize', pasting each URI in turn."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("".join(u + "\n" for u in uris)))
    return cli.run("--initialize", answers=answers)


A = ("GitHub", "me", b"0123456789")
B = ("AWS", "me", b"abcdefghij")


def test_import_creates_encrypted_store(cli, monkeypatch):
    code, out, _ = run_import(cli, monkeypatch, make_uri([A]))
    assert code == 0
    assert "✓ Imported 1 new account\n" in out
    assert undated(cli.load()) == [{"issuer": "GitHub", "name": "me", "secret": b32(A[2]),
                                    "algorithm": "SHA1", "digits": 6}]
    assert b"GitHub" not in cli.secrets.read_bytes()
    assert os.stat(cli.secrets).st_mode & 0o777 == 0o600


def test_import_merges_and_backs_up(cli, monkeypatch):
    run_import(cli, monkeypatch, make_uri([A]))
    code, out, _ = run_import(cli, monkeypatch, make_uri([A, B]))

    assert code == 0
    assert "✓ Imported 1 new account, skipped 1 already present" in out
    assert [a["issuer"] for a in cli.load()] == ["GitHub", "AWS"]
    assert len(list_backups(str(cli.backups))) == 1


def test_import_all_qr_codes_of_a_multi_part_export(cli, monkeypatch):
    code, out, _ = run_import(
        cli, monkeypatch,
        make_uri([A], batch_index=0, batch_size=2),
        make_uri([B], batch_index=1, batch_size=2),
        answers=("y", ""),
    )
    assert code == 0
    assert "QR 2 of 2" in out
    assert [a["issuer"] for a in cli.load()] == ["GitHub", "AWS"]


def test_import_never_prints_secrets(cli, monkeypatch):
    _, out, err = run_import(cli, monkeypatch, make_uri([A]))
    assert b32(A[2]) not in out + err


def make_param_uri(configure):
    payload = migration_pb2.MigrationPayload(batch_index=0, batch_size=1)
    p = payload.otp_parameters.add()
    p.secret = b"0123456789"
    p.issuer = "X"
    p.name = "x"
    configure(p)
    data = base64.b64encode(payload.SerializeToString()).decode()
    return f"otpauth-migration://offline?data={quote(data, safe='')}"


@pytest.mark.parametrize("enum_value, expected", [
    (migration_pb2.ALGORITHM_UNSPECIFIED, "SHA1"),
    (migration_pb2.ALGORITHM_SHA1, "SHA1"),
    (migration_pb2.ALGORITHM_SHA256, "SHA256"),
    (migration_pb2.ALGORITHM_SHA512, "SHA512"),
    (migration_pb2.ALGORITHM_MD5, "MD5"),
])
def test_parse_keeps_algorithm(enum_value, expected):
    uri = make_param_uri(lambda p: setattr(p, "algorithm", enum_value))
    accounts, _, _, _ = parse_migration_uri(uri)
    assert accounts[0]["algorithm"] == expected


@pytest.mark.parametrize("enum_value, expected", [
    (migration_pb2.DIGIT_COUNT_UNSPECIFIED, 6),
    (migration_pb2.DIGIT_COUNT_SIX, 6),
    (migration_pb2.DIGIT_COUNT_EIGHT, 8),
])
def test_parse_keeps_digits(enum_value, expected):
    uri = make_param_uri(lambda p: setattr(p, "digits", enum_value))
    accounts, _, _, _ = parse_migration_uri(uri)
    assert accounts[0]["digits"] == expected


def test_parse_skips_hotp_accounts():
    uri = make_param_uri(lambda p: setattr(p, "type", migration_pb2.OTP_TYPE_HOTP))
    accounts, skipped, _, _ = parse_migration_uri(uri)
    assert accounts == []
    assert skipped == ["X (x)"]


# --- duplicates and date_added ---------------------------------------------------------

def test_merge_matches_on_the_secret_whatever_the_label():
    existing = [{"issuer": "GitHub (renamed)", "name": "work", "secret": "JBSWY3DPEHPK3PXP"}]
    new = [{"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP"},
           {"issuer": "AWS", "name": "me", "secret": "GEZDGNBVGY3TQOJQ"}]
    merged, added = merge_accounts(existing, new)
    assert added == 1
    assert [a["issuer"] for a in merged] == ["GitHub (renamed)", "AWS"]


def test_merge_ignores_case_spaces_and_padding_in_secrets():
    existing = [{"issuer": "GitHub", "name": "me", "secret": "jbsw y3dp ehpk 3pxp"}]
    merged, added = merge_accounts(existing, [{"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP===="}])
    assert added == 0 and merged == existing


def test_merge_skips_duplicates_within_one_import():
    twice = [{"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP"},
             {"issuer": "unknown", "name": "me", "secret": "JBSWY3DPEHPK3PXP"}]
    merged, added = merge_accounts([], twice)
    assert added == 1 and merged == twice[:1]


def test_reimport_after_renaming_adds_no_duplicates(cli, monkeypatch):
    run_import(cli, monkeypatch, make_uri([A, B]))
    renamed = cli.load()
    renamed[0]["issuer"] = "GitHub personal"
    cli.store(renamed)
    code, out, _ = run_import(cli, monkeypatch, make_uri([A, B]))
    assert code == 0
    assert "✓ Imported 0 new accounts, skipped 2 already present" in out
    assert [a["issuer"] for a in cli.load()] == ["GitHub personal", "AWS"]


def test_import_stamps_only_new_accounts(cli, monkeypatch):
    cli.store([{"issuer": "GitHub", "name": "me", "secret": b32(A[2])}])
    run_import(cli, monkeypatch, make_uri([A, B]))
    old, new = cli.load()
    assert "date_added" not in old  # added before otpcli kept dates: left alone
    added = datetime.fromisoformat(new["date_added"])
    assert added.tzinfo is not None
    assert abs((datetime.now(added.tzinfo) - added).total_seconds()) < 60
