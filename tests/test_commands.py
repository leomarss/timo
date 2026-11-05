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
    (["--add"], "add"),
    (["--passwd"], "passwd"),
    (["--forget"], "forget"),
    (["--remember"], "remember"),
    (["--backup"], "backup"),
    (["--remove"], "remove"),
    (["--remove-backups", "a", "b"], "remove-backups"),
    (["--remove-all-backups"], "remove-all-backups"),
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
    ["--editor", "vim"],  # option without its action
    ["--migrate"], ["--yes"],  # removed
    ["--remove-all-backups", "--remove-backups", "x"], ["--remove-backups"],
    ["--remove", "github"],  # --remove picks from a list, it takes no words
    ["--remove-all"], ["--backup", "--remove-all-backups"],  # old backup flags
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
    assert code == 0 and out.startswith("edit (me)\n")


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
    code, out, err = cli.run("--list")
    assert code == 1
    assert out == "" and "doesn't run as root" in err


def test_missing_store_suggests_initialize(cli):
    code, out, err = cli.run("--list")
    assert code == 1
    assert out == "" and "otpcli --initialize" in err


def test_wrong_passphrase(cli, monkeypatch):
    cli.store(ACC, passphrase="something else")
    code, out, err = cli.run("--list")
    assert code == 1
    assert "✗ Wrong passphrase" in err


def test_get_single_match_prints_code(cli):
    cli.store(TWO)
    code, out, _ = cli.run("git", "--no-copy")
    assert code == 0
    label, line = out.splitlines()
    assert label == "GitHub (me)"
    assert line.split()[0].isdigit() and len(line.split()[0]) == 6
    assert "not copied" in line


def test_get_no_match(cli):
    cli.store(TWO)
    code, out, err = cli.run("nothing-matches")
    assert code == 1 and out == ""
    assert err == '✗ No account matches "nothing-matches"\n'


def test_get_with_no_accounts_suggests_initialize(cli):
    cli.store([])
    code, _, err = cli.run()
    assert code == 1 and "No accounts yet" in err and "otpcli --initialize" in err


@pytest.mark.parametrize("accounts, expected", [([], "Total          0   (0 issuers)"), (TWO, "Total          2   (2 issuers)")])
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
    assert code == 0 and "✓ Saved 2 accounts" in out
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
    code, _, err = cli.run("--edit", "--editor", editor)
    assert code == 0 and "No changes" in err


@pytest.mark.parametrize("content", ["not json", '{"a": 1}', '[{"issuer": "x"}]',
                                     '[{"issuer": "x", "name": "y", "secret": "Z", "digits": 7}]'])
def test_edit_rejects_invalid_content(cli, editor, monkeypatch, content):
    cli.store(ACC)
    monkeypatch.setenv("EDIT_CONTENT", content)
    code, _, err = cli.run("--edit", "--editor", editor, answers=["n"])
    assert code == 1
    assert "✗ Invalid accounts" in err and "! Changes discarded" in err
    assert cli.load() == ACC


# --- passwd -----------------------------------------------------------------------

def test_passwd(cli, monkeypatch):
    cli.store(ACC)
    monkeypatch.setattr(commands, "ask_new_passphrase", lambda: "brand new passphrase")
    code, out, _ = cli.run("--passwd")
    assert code == 0 and "✓ Passphrase changed" in out
    assert cli.load("brand new passphrase") == ACC
    assert len(list_backups(str(cli.backups))) == 1


@pytest.mark.parametrize("argv", [["--no-copy", "git"], ["git", "--no-copy"]])
def test_get_options_before_or_after_words(cli, argv):
    cli.store(ACC)
    code, out, _ = cli.run(*argv)
    assert code == 0 and out.startswith("GitHub (me)\n")


@pytest.mark.parametrize("argv", [
    ["github", "--no-copy", "me"],
    ["--no-copy", "github", "me"],
    ["github", "me", "--clear-after", "5"],
])
def test_words_and_options_in_any_order(argv):
    from totp_cli.cli import parse
    args = parse(argv)
    assert args.action == "get" and args.query == ["github", "me"]


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
