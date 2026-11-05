import json

import pytest

from utils import commands
from utils.utils import create_backup, list_backups, restore_backup


# --- bug 8: restore backs up the current file first ---------------------------

@pytest.fixture
def files(tmp_path):
    json_path = tmp_path / "secrets.json"
    backup_dir = tmp_path / "backups"
    return json_path, str(backup_dir)


def test_restore_backs_up_current_file_first(files):
    json_path, backup_dir = files
    json_path.write_text('["old"]')
    backup = create_backup(str(json_path), backup_dir)
    json_path.write_text('["current"]')

    restored, safety = restore_backup(backup.split("/")[-1], backup_dir, str(json_path))

    assert json.loads(json_path.read_text()) == ["old"]
    assert json.loads(open(safety).read()) == ["current"]
    assert len(list_backups(backup_dir)) == 2


def test_restore_of_missing_backup_creates_no_safety_backup(files):
    json_path, backup_dir = files
    json_path.write_text('["current"]')
    with pytest.raises(FileNotFoundError):
        restore_backup("secrets.json.bak.2000-01-01_00-00-00", backup_dir, str(json_path))
    assert list_backups(backup_dir) == []


def test_backups_in_the_same_second_do_not_overwrite_each_other(files):
    json_path, backup_dir = files
    json_path.write_text('["one"]')
    first = create_backup(str(json_path), backup_dir)
    json_path.write_text('["two"]')
    second = create_backup(str(json_path), backup_dir)

    assert first != second
    assert json.loads(open(first).read()) == ["one"]
    assert json.loads(open(second).read()) == ["two"]


# --- bug 9: flags must match exactly ------------------------------------------

def run_flags(tmp_path, capsys, *flags):
    json_path = tmp_path / "secrets.json"
    json_path.write_text("[]")
    with pytest.raises(SystemExit) as exc:
        commands.handle_commands(["app.py", *flags], [], str(json_path), str(tmp_path / "b"), str(tmp_path))
    return exc.value.code, capsys.readouterr().out


@pytest.mark.parametrize("flag", ["--listxyz", "--backupfoo", "--stats2", "--help-me", "-hx", "--editor"])
def test_rejects_flags_that_only_start_with_a_known_flag(tmp_path, capsys, flag):
    code, out = run_flags(tmp_path, capsys, flag)
    assert code == 1
    assert f"{flag} command not found" in out


@pytest.mark.parametrize("flags", [("--list",), ("-h",), ("--stats",)])
def test_accepts_exact_flags(tmp_path, capsys, flags):
    code, out = run_flags(tmp_path, capsys, *flags)
    assert code == 0
    assert "command not found" not in out
