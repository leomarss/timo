import json
import os
import sys

import pytest

from totp_cli import commands
from totp_cli.utils import list_backups

ACC = [{"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP"}]
TWO = ACC + [{"issuer": "AWS", "name": "ops", "secret": "GEZDGNBVGY3TQOJQ"}]


# --- flag parsing -------------------------------------------------------------------

@pytest.mark.parametrize("argv, action", [
    ([], "get"),
    (["github", "me"], "get"),
    (["edit"], "get"),  # plain words are always a search, even command-like ones
    (["list", "--no-copy"], "get"),
    (["--", "-weird"], "get"),
    (["--list"], "list"),
    (["--stats"], "stats"),
    (["--watch"], "watch"),
    (["--edit"], "edit"),
    (["--edit", "--backup", "--editor=vim"], "edit"),
    (["--editor", "vim", "--backup", "--edit"], "edit"),
    (["--initialize"], "initialize"),
    (["--passwd"], "passwd"),
    (["--forget"], "forget"),
    (["--remember"], "remember"),
    (["--migrate", "--yes"], "migrate"),
    (["--backup"], "backup"),
    (["--backup", "--remove", "a", "b"], "remove"),
    (["--remove", "a"], "remove"),
    (["--backup", "--remove-all"], "remove-all"),
    (["--list-backups"], "list-backups"),
    (["--restore", "x"], "restore"),
])
def test_flags_pick_the_action(argv, action):
    from totp_cli.cli import parse
    assert parse(argv).action == action


def test_query_words_are_kept():
    from totp_cli.cli import parse
    args = parse(["--", "-weird", "edit"])
    assert args.query == ["-weird", "edit"]


@pytest.mark.parametrize("argv", [
    ["--listxyz"], ["--backupfoo"], ["--lis"], ["--rem", "x"], ["--editor"],  # unknown, abbreviated, missing value
    ["--list", "--stats"], ["--edit", "--list"], ["--restore", "x", "--backup"],  # two actions
    ["github", "--list"],  # search words with an action
    ["--list", "--no-copy"], ["--stats", "--clear-after", "5"],  # get-only options
    ["--editor", "vim"], ["--yes"], ["--list", "--yes"],  # options without their action
    ["--remove-all", "--remove", "x"],
    ["--clear-after", "-1"], ["--clear-after", "soon"],
])
def test_bad_combinations_are_rejected(argv):
    from totp_cli.cli import parse
    with pytest.raises(SystemExit) as exc:
        parse(argv)
    assert exc.value.code == 2


def test_account_named_like_a_flag_name(cli):
    cli.store([{"issuer": "edit", "name": "me", "secret": "JBSWY3DPEHPK3PXP"}])
    code, out, _ = cli.run("edit", "--no-copy")
    assert code == 0 and "OTP code for edit (me):" in out


def test_help(cli, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.run("-h")
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for flag in ("--list", "--edit", "--restore", "--initialize", "--passwd", "--clear-after"):
        assert flag in out


# --- general ----------------------------------------------------------------------

def test_refuses_to_run_as_root(cli, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    code, out, _ = cli.run("--list")
    assert code == 1
    assert "no longer runs as root" in out


def test_missing_store_suggests_import(cli):
    code, out, _ = cli.run("--list")
    assert code == 1
    assert "otpcli --initialize" in out
    assert "migrate" not in out


def test_missing_store_suggests_migrate_when_old_file_exists(cli):
    cli.legacy_json.parent.mkdir(parents=True)
    cli.legacy_json.write_text(json.dumps(ACC))
    code, out, _ = cli.run("--list")
    assert code == 1
    assert "otpcli --migrate" in out


def test_wrong_passphrase(cli, monkeypatch):
    cli.store(ACC, passphrase="something else")
    code, out, _ = cli.run("--list")
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


@pytest.mark.parametrize("accounts, expected", [([], "Total accounts: 0"), (TWO, "Total accounts: 2")])
def test_stats(cli, accounts, expected):
    cli.store(accounts)
    code, out, _ = cli.run("--stats")
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
    code, out, _ = cli.run("--edit", "--editor", editor)
    assert code == 0 and "Saved 2 account(s)." in out
    assert cli.load() == TWO
    assert list_backups(str(cli.backups)) == []


def test_edit_removes_decrypted_temp_file(cli, editor, monkeypatch, tmp_path):
    cli.store(ACC)
    monkeypatch.setenv("EDIT_CONTENT", json.dumps(TWO))
    cli.run("--edit", "--editor", editor)
    temp = (tmp_path / "seen").read_text()
    assert not os.path.exists(temp)
    assert sorted(p.name for p in cli.secrets.parent.iterdir()) == ["secrets.enc"]


@pytest.mark.parametrize("argv", [
    ["--edit", "--backup", "--editor", "EDITOR"],
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
    code, out, _ = cli.run("--edit", "--editor", editor)
    assert code == 0 and "No changes." in out


@pytest.mark.parametrize("content", ["not json", '{"a": 1}', '[{"issuer": "x"}]',
                                     '[{"issuer": "x", "name": "y", "secret": "Z", "digits": 7}]'])
def test_edit_rejects_invalid_content(cli, editor, monkeypatch, content):
    cli.store(ACC)
    monkeypatch.setenv("EDIT_CONTENT", content)
    code, out, _ = cli.run("--edit", "--editor", editor, answers=["n"])
    assert code == 1
    assert "Invalid secrets" in out and "Changes discarded." in out
    assert cli.load() == ACC


# --- passwd -----------------------------------------------------------------------

def test_passwd(cli, monkeypatch):
    cli.store(ACC)
    monkeypatch.setattr(commands, "ask_new_passphrase", lambda: "brand new passphrase")
    code, out, _ = cli.run("--passwd")
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
    code, out, _ = cli.run("--migrate", answers=["y"])
    assert code == 0
    assert cli.load() == TWO
    assert not cli.legacy_json.exists()
    assert not (cli.legacy_json.parent / "backups").exists()


def test_migrate_can_keep_old_files(cli):
    write_legacy(cli, ACC)
    code, out, _ = cli.run("--migrate", answers=["n"])
    assert code == 0
    assert cli.load() == ACC
    assert cli.legacy_json.exists()


def test_migrate_without_old_file(cli):
    code, out, _ = cli.run("--migrate")
    assert code == 1 and "No old secrets file found" in out


@pytest.mark.parametrize("argv", [["--no-copy", "git"], ["git", "--no-copy"]])
def test_get_options_before_or_after_words(cli, argv):
    cli.store(ACC)
    code, out, _ = cli.run(*argv)
    assert code == 0 and "OTP code for GitHub (me):" in out


@pytest.mark.parametrize("argv", [
    ["github", "--no-copy", "me"],
    ["--no-copy", "github", "me"],
    ["github", "me", "--clear-after", "5"],
])
def test_words_and_options_in_any_order(argv):
    from totp_cli.cli import parse
    args = parse(argv)
    assert args.action == "get" and args.query == ["github", "me"]


def test_migrate_from_explicit_path(cli, tmp_path):
    old = tmp_path / "elsewhere" / "secrets.json"
    old.parent.mkdir()
    old.write_text(json.dumps(TWO))
    code, out, _ = cli.run("--migrate", str(old), answers=["n"])
    assert code == 0
    assert cli.load() == TWO


def test_migrate_reports_where_it_looked(cli):
    code, out, _ = cli.run("--migrate")
    assert code == 1
    assert str(cli.legacy_json) in out
    assert "otpcli --migrate PATH" in out


def test_legacy_lookup_prefers_existing_candidate(tmp_path, monkeypatch):
    from totp_cli import cli as cli_module
    first, second = tmp_path / "a" / "secrets.json", tmp_path / "b" / "secrets.json"
    second.parent.mkdir()
    second.write_text("[]")
    monkeypatch.setattr(cli_module, "legacy_candidates", lambda: [str(first), str(second)])
    assert cli_module.make_context().legacy_json == str(second)
    second.unlink()
    assert cli_module.make_context().legacy_json is None


def test_monitor_script_starts_watch_mode():
    import importlib.util
    import os
    from totp_cli.cli import parse
    path = os.path.join(os.path.dirname(__file__), "..", "src", "monitor.py")
    spec = importlib.util.spec_from_file_location("monitor", path)
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    assert parse(monitor.ARGV).action == "watch"


def test_version(cli, capsys):
    from totp_cli import __version__
    with pytest.raises(SystemExit) as exc:
        cli.run("--version")
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"otpcli {__version__}"
