import json
import os
import sys

import pytest

from utils import commands
from utils.cli import translate_legacy
from utils.utils import list_backups

ACC = [{"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP"}]
TWO = ACC + [{"issuer": "AWS", "name": "ops", "secret": "GEZDGNBVGY3TQOJQ"}]


# --- old flags --------------------------------------------------------------------

@pytest.mark.parametrize("old, new", [
    (["--initialize"], ["import"]),
    (["--list"], ["list"]),
    (["--stats"], ["stats"]),
    (["--list-backups"], ["backup", "list"]),
    (["--backup"], ["backup", "create"]),
    (["--backup", "--remove", "a", "b"], ["backup", "remove", "a", "b"]),
    (["--backup", "--remove-all"], ["backup", "remove", "--all"]),
    (["--restore", "x"], ["backup", "restore", "x"]),
    (["--edit"], ["edit"]),
    (["--edit", "--editor=vim", "--backup"], ["edit", "--backup", "--editor", "vim"]),
    (["--editor=vim", "--backup", "--edit"], ["edit", "--backup", "--editor", "vim"]),
])
def test_legacy_flags_translate(old, new):
    translated, hint = translate_legacy(old)
    assert translated == new
    assert f"otpcli {' '.join(new)}" in hint


@pytest.mark.parametrize("argv", [[], ["github"], ["list"], ["backup", "remove", "--all"], ["-h"]])
def test_new_style_is_left_alone(argv):
    assert translate_legacy(argv) == (argv, None)


def test_legacy_flag_prints_hint_and_works(cli):
    cli.store(TWO)
    code, out, err = cli.run("--list")
    assert code == 0
    assert out.splitlines() == ["GitHub (me)", "AWS (ops)"]
    assert "is now 'otpcli list'" in err


@pytest.mark.parametrize("argv", [["--listxyz"], ["--backupfoo"], ["list", "--nope"], ["--editor"]])
def test_unknown_flags_are_rejected(cli, argv):
    with pytest.raises(SystemExit) as exc:
        cli.run(*argv)
    assert exc.value.code == 2


# --- general ----------------------------------------------------------------------

def test_refuses_to_run_as_root(cli, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    code, out, _ = cli.run("list")
    assert code == 1
    assert "no longer runs as root" in out


def test_missing_store_suggests_import(cli):
    code, out, _ = cli.run("list")
    assert code == 1
    assert "otpcli import" in out
    assert "migrate" not in out


def test_missing_store_suggests_migrate_when_old_file_exists(cli):
    cli.legacy_json.parent.mkdir(parents=True)
    cli.legacy_json.write_text(json.dumps(ACC))
    code, out, _ = cli.run("list")
    assert code == 1
    assert "otpcli migrate" in out


def test_wrong_passphrase(cli, monkeypatch):
    cli.store(ACC, passphrase="something else")
    code, out, _ = cli.run("list")
    assert code == 1
    assert "Wrong passphrase" in out


def test_get_single_match_prints_code(cli):
    cli.store(TWO)
    code, out, _ = cli.run("git", "--no-copy")
    assert code == 0
    assert "OTP code for GitHub (me):" in out
    assert "not copied" in out


def test_get_no_match(cli):
    cli.store(TWO)
    code, out, _ = cli.run("nothing-matches")
    assert code == 1 and "No matching accounts found." in out


def test_account_named_like_a_command_via_get(cli):
    cli.store([{"issuer": "list", "name": "me", "secret": "JBSWY3DPEHPK3PXP"}])
    code, out, _ = cli.run("get", "list", "--no-copy")
    assert code == 0 and "OTP code for list (me):" in out


@pytest.mark.parametrize("accounts, expected", [([], "Total accounts: 0"), (TWO, "Total accounts: 2")])
def test_stats(cli, accounts, expected):
    cli.store(accounts)
    code, out, _ = cli.run("stats")
    assert code == 0 and expected in out


# --- edit -------------------------------------------------------------------------

@pytest.fixture
def editor(tmp_path, monkeypatch):
    """A fake editor that writes $EDIT_CONTENT into the file (or leaves it alone)."""
    script = tmp_path / "fake_editor.py"
    script.write_text(
        "import os, sys\n"
        "content = os.environ.get('EDIT_CONTENT')\n"
        "if content is not None:\n"
        "    open(sys.argv[1], 'w').write(content)\n"
        "open(os.environ['SEEN_PATH'], 'w').write(sys.argv[1])\n"
    )
    monkeypatch.setenv("SEEN_PATH", str(tmp_path / "seen"))
    return f"{sys.executable} {script}"


def test_edit_saves_valid_changes(cli, editor, monkeypatch):
    cli.store(ACC)
    monkeypatch.setenv("EDIT_CONTENT", json.dumps(TWO))
    code, out, _ = cli.run("edit", "--editor", editor)
    assert code == 0 and "Saved 2 account(s)." in out
    assert cli.load() == TWO
    assert list_backups(str(cli.backups)) == []


def test_edit_removes_decrypted_temp_file(cli, editor, monkeypatch, tmp_path):
    cli.store(ACC)
    monkeypatch.setenv("EDIT_CONTENT", json.dumps(TWO))
    cli.run("edit", "--editor", editor)
    temp = (tmp_path / "seen").read_text()
    assert not os.path.exists(temp)
    assert sorted(p.name for p in cli.secrets.parent.iterdir()) == ["secrets.enc"]


@pytest.mark.parametrize("argv", [
    ["edit", "--backup", "--editor", "EDITOR"],
    ["--edit", "--editor=EDITOR", "--backup"],  # old order that used to skip the backup
])
def test_edit_with_backup(cli, editor, monkeypatch, argv):
    cli.store(ACC)
    monkeypatch.setenv("EDIT_CONTENT", json.dumps(TWO))
    argv = [a.replace("EDITOR", editor) for a in argv]
    code, out, _ = cli.run(*argv)
    assert code == 0
    assert len(list_backups(str(cli.backups))) == 1


def test_edit_without_changes(cli, editor):
    cli.store(ACC)
    code, out, _ = cli.run("edit", "--editor", editor)
    assert code == 0 and "No changes." in out


@pytest.mark.parametrize("content", ["not json", '{"a": 1}', '[{"issuer": "x"}]',
                                     '[{"issuer": "x", "name": "y", "secret": "Z", "digits": 7}]'])
def test_edit_rejects_invalid_content(cli, editor, monkeypatch, content):
    cli.store(ACC)
    monkeypatch.setenv("EDIT_CONTENT", content)
    code, out, _ = cli.run("edit", "--editor", editor, answers=["n"])
    assert code == 1
    assert "Invalid secrets" in out and "Changes discarded." in out
    assert cli.load() == ACC


# --- passwd -----------------------------------------------------------------------

def test_passwd(cli, monkeypatch):
    cli.store(ACC)
    monkeypatch.setattr(commands, "ask_new_passphrase", lambda: "brand new passphrase")
    code, out, _ = cli.run("passwd")
    assert code == 0 and "Passphrase changed." in out
    assert cli.load("brand new passphrase") == ACC
    assert len(list_backups(str(cli.backups))) == 1


# --- migrate ----------------------------------------------------------------------

def write_legacy(cli, accounts):
    cli.legacy_json.parent.mkdir(parents=True)
    cli.legacy_json.write_text(json.dumps(accounts))
    backups = cli.legacy_json.parent / "backups"
    backups.mkdir()
    (backups / "secrets.json.bak.2025-01-01_00-00-00").write_text(json.dumps(accounts))


def test_migrate_imports_and_deletes_plaintext(cli):
    write_legacy(cli, TWO)
    code, out, _ = cli.run("migrate", answers=["y"])
    assert code == 0
    assert cli.load() == TWO
    assert not cli.legacy_json.exists()
    assert not (cli.legacy_json.parent / "backups").exists()


def test_migrate_can_keep_old_files(cli):
    write_legacy(cli, ACC)
    code, out, _ = cli.run("migrate", answers=["n"])
    assert code == 0
    assert cli.load() == ACC
    assert cli.legacy_json.exists()


def test_migrate_without_old_file(cli):
    code, out, _ = cli.run("migrate")
    assert code == 1 and "Nothing to migrate" in out


@pytest.mark.parametrize("argv", [["--no-copy", "git"], ["--no-copy"]])
def test_get_options_without_command_name(cli, argv):
    cli.store(ACC)
    code, out, _ = cli.run(*argv)
    assert code == 0 and "OTP code for GitHub (me):" in out
