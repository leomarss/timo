import io
import sys

import pytest

from totp_cli import clipboard, commands
from totp_cli.otpauth import normalize_secret, parse_otpauth_uri
from totp_cli.utils import list_backups

SECRET = "JBSWY3DPEHPK3PXP"
OTHER = "GEZDGNBVGY3TQOJQ"


# --- parsing -----------------------------------------------------------------------

def test_parse_full_uri():
    acc = parse_otpauth_uri(
        f"otpauth://totp/GitHub:me%40x.com?secret={SECRET}&issuer=GitHub&algorithm=SHA256&digits=8&period=30"
    )
    assert acc == {"issuer": "GitHub", "name": "me@x.com", "secret": SECRET,
                   "algorithm": "SHA256", "digits": 8}


def test_parse_defaults_to_sha1_and_six_digits():
    acc = parse_otpauth_uri(f"otpauth://totp/me?secret={SECRET}")
    assert acc == {"issuer": "", "name": "me", "secret": SECRET, "algorithm": "SHA1", "digits": 6}


def test_issuer_parameter_wins_over_label_prefix():
    acc = parse_otpauth_uri(f"otpauth://totp/Old%20Name:me?secret={SECRET}&issuer=New%20Name")
    assert (acc["issuer"], acc["name"]) == ("New Name", "me")


def test_issuer_from_label_when_no_parameter():
    acc = parse_otpauth_uri(f"otpauth://totp/ACME%20Co:%20john?secret={SECRET}")
    assert (acc["issuer"], acc["name"]) == ("ACME Co", "john")


@pytest.mark.parametrize("uri, error", [
    ("https://example.com", "Not an otpauth:// link"),
    (f"otpauth://hotp/me?secret={SECRET}&counter=1", "HOTP"),
    ("otpauth://totp/me?issuer=x", "no secret key"),
    (f"otpauth://totp/me?secret={SECRET}&period=60", "30-second"),
    (f"otpauth://totp/me?secret={SECRET}&digits=many", "digits"),
])
def test_parse_rejects(uri, error):
    with pytest.raises(ValueError, match=error):
        parse_otpauth_uri(uri)


@pytest.mark.parametrize("text", ["jbsw y3dp ehpk 3pxp", "JBSW-Y3DP-EHPK-3PXP", "JBSWY3DPEHPK3PXP===="])
def test_normalize_secret(text):
    assert normalize_secret(text) == SECRET


@pytest.mark.parametrize("text", ["", "   ", "not base32!", "JBSWY3DPEHPK3PX18"])
def test_normalize_secret_rejects(text):
    with pytest.raises(ValueError):
        normalize_secret(text)


# --- the command -------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_clipboard(monkeypatch):
    monkeypatch.setattr(clipboard, "copy", lambda text: False)


def run_add(cli, monkeypatch, pasted=None, answers=("y",)):
    """Run 'otpcli --add'; `pasted` is what goes into the hidden prompt."""
    if pasted is not None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(pasted + "\n"))
    return cli.run("--add", answers=answers)


def test_add_otpauth_link_creates_store(cli, monkeypatch):
    code, out, err = run_add(cli, monkeypatch, f"otpauth://totp/GitHub:me?secret={SECRET}&issuer=GitHub")
    assert code == 0, err
    assert "✓ Added GitHub (me)" in out
    assert cli.load() == [{"issuer": "GitHub", "name": "me", "secret": SECRET,
                           "algorithm": "SHA1", "digits": 6}]


def test_add_shows_the_current_code(cli, monkeypatch):
    _, out, _ = run_add(cli, monkeypatch, f"otpauth://totp/GitHub:me?secret={SECRET}")
    label, line = out.splitlines()[:2]
    assert label == "GitHub (me)"
    assert line.split()[0].isdigit() and len(line.split()[0]) == 6


def test_add_secret_key_asks_for_issuer_and_name(cli, monkeypatch):
    code, out, err = run_add(cli, monkeypatch, "jbsw y3dp ehpk 3pxp", answers=("y", "GitHub", "me"))
    assert code == 0, err
    assert cli.load() == [{"issuer": "GitHub", "name": "me", "secret": SECRET,
                           "algorithm": "SHA1", "digits": 6}]


def test_add_asks_again_for_empty_issuer(cli, monkeypatch):
    code, _, err = run_add(cli, monkeypatch, SECRET, answers=("y", "", "  ", "GitHub", "me"))
    assert code == 0, err
    assert cli.load()[0]["issuer"] == "GitHub"


def test_add_link_without_issuer_asks_for_it(cli, monkeypatch):
    code, _, err = run_add(cli, monkeypatch, f"otpauth://totp/me?secret={SECRET}", answers=("y", "GitHub"))
    assert code == 0, err
    assert (cli.load()[0]["issuer"], cli.load()[0]["name"]) == ("GitHub", "me")


def test_add_from_qr_code(cli, monkeypatch):
    monkeypatch.setattr(commands, "scan_qr_image", lambda: f"otpauth://totp/AWS:me?secret={SECRET}")
    code, out, err = run_add(cli, monkeypatch, answers=("n",))
    assert code == 0, err
    assert "✓ Added AWS (me)" in out
    assert cli.load()[0]["issuer"] == "AWS"


def test_add_unreadable_qr_adds_nothing(cli, monkeypatch):
    monkeypatch.setattr(commands, "scan_qr_image", lambda: None)
    code, _, err = run_add(cli, monkeypatch, answers=("",))
    assert code == 1
    assert "✗ Nothing added" in err
    assert not cli.secrets.exists()


def test_add_migration_export_points_to_initialize(cli, monkeypatch):
    code, _, err = run_add(cli, monkeypatch, "otpauth-migration://offline?data=abc")
    assert code == 1
    assert "otpcli --initialize" in err


def test_add_rejects_bad_key(cli, monkeypatch):
    code, _, err = run_add(cli, monkeypatch, "not a key!")
    assert code == 1
    assert "✗" in err
    assert not cli.secrets.exists()


def test_add_rejects_unsupported_algorithm(cli, monkeypatch):
    code, _, err = run_add(cli, monkeypatch, f"otpauth://totp/A:me?secret={SECRET}&algorithm=SHA3")
    assert code == 1
    assert "Unsupported algorithm" in err


def test_add_appends_and_backs_up(cli, monkeypatch):
    cli.store([{"issuer": "AWS", "name": "me", "secret": OTHER}])
    code, out, _ = run_add(cli, monkeypatch, f"otpauth://totp/GitHub:me?secret={SECRET}")
    assert code == 0
    assert "✓ Previous secrets backed up" in out
    assert [a["issuer"] for a in cli.load()] == ["AWS", "GitHub"]
    assert len(list_backups(str(cli.backups))) == 1


def test_add_same_account_twice_changes_nothing(cli, monkeypatch):
    cli.store([{"issuer": "GitHub", "name": "me", "secret": SECRET}])
    code, _, err = run_add(cli, monkeypatch, f"otpauth://totp/GitHub:me?secret={SECRET}")
    assert code == 0
    assert "GitHub (me) is already present" in err
    assert len(cli.load()) == 1
    assert list_backups(str(cli.backups)) == []


def test_add_new_key_for_existing_account_replaces_it(cli, monkeypatch):
    cli.store([{"issuer": "GitHub", "name": "me", "secret": OTHER},
               {"issuer": "AWS", "name": "me", "secret": OTHER}])
    code, out, _ = run_add(cli, monkeypatch, f"otpauth://totp/github:me?secret={SECRET}", answers=("y", "y"))
    assert code == 0
    assert "✓ Replaced GitHub (me)" in out
    accounts = cli.load()
    assert [a["issuer"] for a in accounts] == ["GitHub", "AWS"]  # keeps the label you had
    assert accounts[0]["secret"] == SECRET
    assert len(list_backups(str(cli.backups))) == 1


def test_add_new_key_for_existing_account_can_be_declined(cli, monkeypatch):
    cli.store([{"issuer": "GitHub", "name": "me", "secret": OTHER}])
    code, _, err = run_add(cli, monkeypatch, f"otpauth://totp/GitHub:me?secret={SECRET}", answers=("y", ""))
    assert code == 1
    assert "✗ Nothing added" in err
    assert cli.load()[0]["secret"] == OTHER


def test_add_never_prints_secrets(cli, monkeypatch):
    _, out, err = run_add(cli, monkeypatch, f"otpauth://totp/GitHub:me?secret={SECRET}")
    assert SECRET not in out + err
