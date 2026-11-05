import os

import pytest

from totp_cli.utils import create_backup, list_backups, resolve_backup_path

ACC = [{"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP"}]
OTHER = [{"issuer": "AWS", "name": "me", "secret": "GEZDGNBVGY3TQOJQ"}]


# --- name validation -------------------------------------------------------------

@pytest.fixture
def backup_dir(tmp_path):
    d = tmp_path / "backups"
    d.mkdir()
    (d / "secrets.enc.bak.2025-01-01_00-00-00").write_text("x")
    return str(d)


def test_resolves_valid_backup_name(backup_dir):
    name = "secrets.enc.bak.2025-01-01_00-00-00"
    assert resolve_backup_path(backup_dir, name) == os.path.join(os.path.realpath(backup_dir), name)


@pytest.mark.parametrize("name", [
    "../secrets.enc",
    "../../etc/passwd",
    "/etc/passwd",
    "secrets.enc.bak.x/../../evil",
    "secrets.json.bak.2025-01-01_00-00-00",
    "notabackup.txt",
    "",
])
def test_rejects_paths_outside_backup_dir_or_bad_names(backup_dir, name):
    with pytest.raises(ValueError):
        resolve_backup_path(backup_dir, name)


def test_backups_in_the_same_second_do_not_overwrite_each_other(tmp_path):
    src = tmp_path / "secrets.enc"
    src.write_text("one")
    first = create_backup(str(src), str(tmp_path / "b"))
    src.write_text("two")
    second = create_backup(str(src), str(tmp_path / "b"))
    assert first != second
    assert open(first).read() == "one"
    assert open(second).read() == "two"


# --- commands --------------------------------------------------------------------

def test_backup_create_and_list(cli):
    cli.store(ACC)
    code, out, _ = cli.run("--backup")
    assert code == 0 and "✓ Backup saved  " in out
    code, out, _ = cli.run("--list-backups")
    assert code == 0 and "secrets.enc.bak." in out


def test_backup_list_without_backup_dir(cli):
    code, out, err = cli.run("--list-backups")
    assert code == 0 and out == "" and "No backups yet" in err


def test_restore_backs_up_current_first(cli):
    cli.store(ACC)
    cli.run("--backup")
    name = list_backups(str(cli.backups))[0]
    cli.store(OTHER)

    code, out, _ = cli.run("--restore", name)

    assert code == 0
    assert "✓ Previous secrets backed up" in out
    assert cli.load() == ACC
    assert len(list_backups(str(cli.backups))) == 2


def test_restore_backup_made_with_older_passphrase(cli, monkeypatch):
    cli.store(ACC, passphrase="old passphrase")
    cli.run("--backup")  # backup copies the file as-is
    name = list_backups(str(cli.backups))[0]
    cli.store(OTHER)  # current store uses the test passphrase

    from totp_cli import commands
    asked = []
    real_ask = commands._ask

    def ask(prompt):
        if "older passphrase" in prompt:
            asked.append(prompt)
            return "old passphrase"
        return real_ask(prompt)

    monkeypatch.setattr(commands, "_ask", ask)
    code, out, _ = cli.run("--restore", name)

    assert code == 0, out
    assert asked
    assert cli.load() == ACC  # re-encrypted with the current passphrase


@pytest.mark.parametrize("name", ["../../etc/passwd", "secrets.enc.bak.2000-01-01_00-00-00"])
def test_restore_rejects_bad_or_missing_names(cli, name):
    cli.store(ACC)
    code, out, _ = cli.run("--restore", name)
    assert code == 1
    assert cli.load() == ACC
    assert list_backups(str(cli.backups)) == []


def test_remove_rejects_traversal(cli, tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    code, out, err = cli.run("--backup", "--remove", "../../victim.txt")
    assert "! Skipped Invalid backup name" in err
    assert victim.read_text() == "keep"


def test_remove_all_without_backup_dir(cli):
    code, out, err = cli.run("--backup", "--remove-all")
    assert code == 0 and "No backups to remove" in err


def test_remove_all_deletes_only_backups(cli):
    cli.store(ACC)
    cli.run("--backup")
    (cli.backups / "notes.txt").write_text("mine")
    code, out, _ = cli.run("--backup", "--remove-all", answers=["y"])
    assert code == 0
    assert list_backups(str(cli.backups)) == []
    assert (cli.backups / "notes.txt").exists()
