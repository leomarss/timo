import base64
import json
import os
from urllib.parse import quote

import pytest

import migration_pb2
from utils.protobuf.extract_google_otp_from_qr import parse_migration_uri
from utils.utils import import_accounts, list_backups


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


@pytest.fixture
def paths(tmp_path):
    return str(tmp_path / "json" / "secrets.json"), str(tmp_path / "json" / "backups")


def read(path):
    with open(path) as f:
        return json.load(f)


def test_import_creates_file_with_private_permissions(paths):
    json_path, backup_dir = paths
    new = [{"issuer": "A", "name": "a", "secret": "AAAA"}]
    added = import_accounts(new, json_path, backup_dir)
    assert added == 1
    assert read(json_path) == new
    assert os.stat(json_path).st_mode & 0o777 == 0o600


def test_import_merges_instead_of_overwriting(paths):
    json_path, backup_dir = paths
    existing = [{"issuer": "Old", "name": "o", "secret": "OOOO"}]
    import_accounts(existing, json_path, backup_dir)

    added = import_accounts([{"issuer": "New", "name": "n", "secret": "NNNN"}], json_path, backup_dir)

    assert added == 1
    assert read(json_path) == existing + [{"issuer": "New", "name": "n", "secret": "NNNN"}]


def test_import_backs_up_existing_file(paths):
    json_path, backup_dir = paths
    import_accounts([{"issuer": "Old", "name": "o", "secret": "OOOO"}], json_path, backup_dir)
    assert list_backups(backup_dir) == []

    import_accounts([{"issuer": "New", "name": "n", "secret": "NNNN"}], json_path, backup_dir)

    backups = list_backups(backup_dir)
    assert len(backups) == 1
    assert read(os.path.join(backup_dir, backups[0])) == [{"issuer": "Old", "name": "o", "secret": "OOOO"}]


def test_import_skips_duplicates(paths):
    json_path, backup_dir = paths
    acc = {"issuer": "A", "name": "a", "secret": "AAAA"}
    import_accounts([acc], json_path, backup_dir)
    added = import_accounts([acc], json_path, backup_dir)
    assert added == 0
    assert read(json_path) == [acc]


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
