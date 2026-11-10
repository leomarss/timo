import os

import pytest

from timo import commands
from timo.utils import list_backups

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
    (["--watch"], "watch"),
    (["--edit"], "edit"),
    (["--edit", "github", "me"], "edit"),
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
    from timo.cli import parse
    assert parse(argv).action == action


def test_query_words_are_kept():
    from timo.cli import parse
    args = parse(["--", "-weird", "edit"])
    assert args.query == ["-weird", "edit"]


@pytest.mark.parametrize("argv", [
    ["--listxyz"], ["--backupfoo"], ["--lis"], ["--rem", "x"], ["--editor"],  # unknown, abbreviated, missing value
    ["--list", "--watch"], ["--edit", "--list"], ["--restore", "x", "--backup"],  # two actions
    ["github", "--list"],  # search words with an action
    ["--list", "--no-copy"], ["--watch", "--clear-after", "5"],  # get-only options
    ["--editor", "vim"], ["--edit", "--editor=vim"],  # removed: --edit is guided now
    ["--edit", "--backup"],  # --edit always backs up
    ["--migrate"], ["--yes"], ["--stats"],  # removed
    ["--remove-all-backups", "--remove-backups", "x"], ["--remove-backups"],
    ["--remove", "github"],  # --remove picks from a list, it takes no words
    ["--remove-all"], ["--backup", "--remove-all-backups"],  # old backup flags
    ["--clear-after", "-1"], ["--clear-after", "soon"],
])
def test_bad_combinations_are_rejected(argv):
    from timo.cli import parse
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
    assert out == "" and "timo --initialize" in err


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
    assert code == 1 and "No accounts yet" in err and "timo --initialize" in err


def test_watch_with_no_accounts_suggests_initialize(cli):
    cli.store([])
    code, out, err = cli.run("--watch")
    assert code == 1 and out == ""
    assert "No accounts yet" in err and "timo --initialize" in err


# --- edit -------------------------------------------------------------------------
# questions in order: issuer, name, secret key (hidden), then save?

@pytest.fixture
def no_fzf(monkeypatch):
    monkeypatch.setattr(commands, "_find_fzf", lambda: False)


@pytest.fixture
def hidden(monkeypatch):
    """Answers for the hidden secret key question, in order; Enter once they run out."""
    answers = []
    monkeypatch.setattr(commands, "read_hidden", lambda prompt: answers.pop(0) if answers else "")
    return answers


def test_edit_renames_the_only_match(cli, hidden):
    cli.store(TWO)
    code, out, err = cli.run("--edit", "github", answers=["", "work", "y"])
    assert code == 0, err
    assert "Editing GitHub (me)" in out
    assert "Name: me → work" in out
    assert "✓ Saved GitHub (work)" in out
    assert cli.load() == [{**ACC[0], "name": "work"}, TWO[1]]
    assert len(list_backups(str(cli.backups))) == 1


def test_edit_enter_keeps_every_value(cli, hidden):
    cli.store(ACC)
    code, _, err = cli.run("--edit", answers=["", ""])
    assert code == 0 and "No changes" in err
    assert cli.load() == ACC
    assert list_backups(str(cli.backups)) == []


def test_edit_every_field(cli, hidden):
    cli.store([{**ACC[0], "algorithm": "SHA256", "digits": 8}])
    hidden.append("gezd gnbv gy3t qojq")
    code, out, err = cli.run("--edit", answers=["GitLab", "work", "y"])
    assert code == 0, err
    assert "Issuer: GitHub → GitLab" in out and "Name: me → work" in out and "Secret key: changed" in out
    assert cli.load() == [{"issuer": "GitLab", "name": "work", "secret": "GEZDGNBVGY3TQOJQ",
                           "algorithm": "SHA256", "digits": 8}]  # algorithm and digits kept as they were


def test_edit_never_shows_the_secret(cli, hidden):
    cli.store(ACC)
    hidden.append("gezd gnbv gy3t qojq")
    _, out, err = cli.run("--edit", answers=["", "", "y"])
    assert ACC[0]["secret"] not in out + err and "GEZDGNBVGY3TQOJQ" not in out + err


def test_edit_asks_again_after_a_bad_secret(cli, hidden):
    cli.store(ACC)
    hidden.extend(["not a key!", "GEZDGNBVGY3TQOJQ"])
    code, _, err = cli.run("--edit", answers=["", "", "y"])
    assert "doesn't look like a secret key" in err
    assert cli.load()[0]["secret"] == "GEZDGNBVGY3TQOJQ"


def test_edit_refuses_a_label_another_account_has(cli, hidden):
    cli.store(TWO)
    code, _, err = cli.run("--edit", "aws", answers=["github", "ME", "", ""])
    assert "GitHub (me) already exists" in err
    assert cli.load()[1] == {**TWO[1], "issuer": "github"}  # the issuer alone was fine


def test_edit_keeps_a_label_two_accounts_already_share(cli, hidden, no_fzf):
    twins = [ACC[0], {**ACC[0], "secret": "GEZDGNBVGY3TQOJQ"}]
    cli.store(twins)
    code, _, err = cli.run("--edit", answers=["1", "", ""])
    assert code == 0 and "No changes" in err and "already exists" not in err
    assert cli.load() == twins


def test_edit_refuses_a_secret_another_account_has(cli, hidden):
    cli.store(TWO)
    hidden.extend([ACC[0]["secret"].lower(), ""])
    _, _, err = cli.run("--edit", "aws", answers=["", ""])
    assert "That secret key belongs to GitHub (me)" in err
    assert cli.load() == TWO


def test_edit_can_be_discarded_at_the_end(cli, hidden):
    cli.store(ACC)
    code, _, err = cli.run("--edit", answers=["", "work", "n"])
    assert code == 0 and "Changes discarded" in err
    assert cli.load() == ACC
    assert list_backups(str(cli.backups)) == []


def test_edit_picks_by_number_among_the_matches(cli, hidden, no_fzf):
    three = TWO + [{"issuer": "GitHub", "name": "work", "secret": "MFRGGZDFMZTWQ2LK"}]
    cli.store(three)
    code, out, err = cli.run("--edit", "github", answers=["2", "", "job", "y"])
    assert code == 0, err
    assert out.splitlines()[:2] == ["1  GitHub (me)", "2  GitHub (work)"]
    assert [a["name"] for a in cli.load()] == ["me", "ops", "job"]


def test_edit_cancelled_at_the_picker(cli, no_fzf):
    cli.store(TWO)
    code, _, err = cli.run("--edit", answers=[""])
    assert code == 0 and "Nothing changed" in err
    assert cli.load() == TWO


def test_edit_without_a_match(cli):
    cli.store(TWO)
    code, _, err = cli.run("--edit", "nope")
    assert code == 1 and "nope" in err


def test_edit_writes_no_decrypted_files(cli, hidden):
    cli.store(ACC)
    cli.run("--edit", answers=["", "work", "y"])
    assert sorted(p.name for p in cli.secrets.parent.iterdir()) == ["backups", "secrets.enc"]


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
    from timo.cli import parse
    args = parse(argv)
    assert args.action == "get" and args.query == ["github", "me"]


def test_version(cli, capsys):
    from timo import __version__
    with pytest.raises(SystemExit) as exc:
        cli.run("--version")
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"timo {__version__}"
