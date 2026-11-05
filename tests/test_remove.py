import subprocess

import pytest

from totp_cli import commands
from totp_cli.utils import list_backups

THREE = [
    {"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP"},
    {"issuer": "AWS", "name": "ops", "secret": "GEZDGNBVGY3TQOJQ"},
    {"issuer": "GitHub", "name": "work", "secret": "MFRGGZDFMZTWQ2LK"},
]


@pytest.fixture
def no_fzf(monkeypatch):
    monkeypatch.setattr(commands, "_find_fzf", lambda: False)


@pytest.fixture
def fzf(monkeypatch):
    """Fake fzf: picks the line whose shown text starts with `fzf.pick` (None = Esc)."""
    class Fake:
        pick = None
        lines = None

    def run(cmd, input, **kwargs):
        Fake.lines = input.splitlines()
        Fake.cmd = cmd
        chosen = [line for line in Fake.lines if Fake.pick and line.split("\t")[1].startswith(Fake.pick + " ")]
        if not chosen:
            raise subprocess.CalledProcessError(130, cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=chosen[0] + "\n")

    monkeypatch.setattr(commands, "_find_fzf", lambda: True)
    monkeypatch.setattr(commands.subprocess, "run", run)
    return Fake


# --- guided (no fzf) ---------------------------------------------------------------

def test_guided_lists_accounts_numbered(cli, no_fzf):
    cli.store(THREE)
    _, out, _ = cli.run("--remove", answers=[""])
    assert out.splitlines()[:3] == ["1  GitHub (me)", "2  AWS (ops)", "3  GitHub (work)"]


def test_guided_removes_the_chosen_account_after_confirming(cli, no_fzf):
    cli.store(THREE)
    code, out, err = cli.run("--remove", answers=["2", "y"])
    assert code == 0, err
    assert "✓ Removed AWS (ops)" in out
    assert "✓ Previous secrets backed up" in out
    assert [a["name"] for a in cli.load()] == ["me", "work"]
    assert len(list_backups(str(cli.backups))) == 1


@pytest.mark.parametrize("answer", ["", "n", "no"])
def test_guided_confirmation_defaults_to_no(cli, no_fzf, answer):
    cli.store(THREE)
    code, _, err = cli.run("--remove", answers=["2", answer])
    assert code == 0
    assert "Nothing removed" in err
    assert cli.load() == THREE
    assert list_backups(str(cli.backups)) == []


def test_guided_empty_number_cancels(cli, no_fzf):
    cli.store(THREE)
    code, _, err = cli.run("--remove", answers=[""])
    assert code == 0 and "Nothing removed" in err
    assert cli.load() == THREE


def test_guided_asks_again_for_a_bad_number(cli, no_fzf):
    cli.store(THREE)
    code, _, err = cli.run("--remove", answers=["0", "4", "two", "3", "y"])
    assert code == 0
    assert err.count("Type a number from 1 to 3") == 3
    assert [a["name"] for a in cli.load()] == ["me", "ops"]


def test_removing_the_last_account_leaves_an_empty_store(cli, no_fzf):
    cli.store(THREE[:1])
    code, _, _ = cli.run("--remove", answers=["1", "y"])
    assert code == 0
    assert cli.load() == []


# --- with fzf ----------------------------------------------------------------------

def test_fzf_removes_the_picked_account_after_confirming(cli, fzf):
    cli.store(THREE)
    fzf.pick = "GitHub (work)"
    code, out, err = cli.run("--remove", answers=["y"])
    assert code == 0, err
    assert "✓ Removed GitHub (work)" in out
    assert [a["name"] for a in cli.load()] == ["me", "ops"]
    assert "--prompt=Remove account: " in fzf.cmd


def test_fzf_offers_every_account(cli, fzf):
    cli.store(THREE)
    cli.run("--remove")
    assert [line.split("\t")[1].split("  ")[0] for line in fzf.lines] == ["GitHub (me)", "AWS (ops)", "GitHub (work)"]


def test_fzf_shows_when_each_account_was_added(cli, fzf):
    accounts = [dict(THREE[0], date_added="2026-11-05T16:02:11+01:00"), THREE[1]]
    cli.store(accounts)
    cli.run("--remove")
    assert [line.split("\t")[1] for line in fzf.lines] == ["GitHub (me)   2026-11-05", "AWS (ops)     -"]


def test_fzf_confirmation_can_be_declined(cli, fzf):
    cli.store(THREE)
    fzf.pick = "AWS (ops)"
    code, _, err = cli.run("--remove", answers=["n"])
    assert code == 0 and "Nothing removed" in err
    assert cli.load() == THREE


def test_fzf_escape_removes_nothing(cli, fzf):
    cli.store(THREE)
    code, _, err = cli.run("--remove")
    assert code == 0 and "Nothing removed" in err
    assert cli.load() == THREE


def test_fzf_duplicate_labels_remove_the_picked_one(cli, fzf, monkeypatch):
    twins = [dict(THREE[0]), dict(THREE[0], secret="MFRGGZDFMZTWQ2LK")]
    cli.store(twins)

    def run(cmd, input, **kwargs):  # pick the second of two identical labels
        return subprocess.CompletedProcess(cmd, 0, stdout=input.splitlines()[1] + "\n")

    monkeypatch.setattr(commands.subprocess, "run", run)
    code, _, _ = cli.run("--remove", answers=["y"])
    assert code == 0
    assert cli.load() == twins[:1]


# --- either way --------------------------------------------------------------------

def test_remove_with_no_accounts(cli, no_fzf):
    cli.store([])
    code, _, err = cli.run("--remove")
    assert code == 1 and "No accounts yet" in err


def test_remove_without_store(cli, no_fzf):
    code, _, err = cli.run("--remove")
    assert code == 1 and "No secrets found" in err


def test_remove_never_prints_secrets(cli, no_fzf):
    cli.store(THREE)
    _, out, err = cli.run("--remove", answers=["1", "y"])
    assert all(acc["secret"] not in out + err for acc in THREE)
