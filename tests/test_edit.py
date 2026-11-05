import os

import pytest

from utils import commands
from utils.utils import list_backups


class Exec(Exception):
    pass


@pytest.fixture
def setup(tmp_path, monkeypatch):
    json_path = tmp_path / "json" / "secrets.json"
    json_path.parent.mkdir()
    json_path.write_text("[]")
    backup_dir = str(tmp_path / "json" / "backups")

    calls = []

    def fake_execvp(file, args):
        calls.append(args)
        raise Exec()

    monkeypatch.setattr(commands.os, "execvp", fake_execvp)
    monkeypatch.setattr(commands.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.delenv("EDITOR", raising=False)

    def run(*flags):
        with pytest.raises(Exec):
            commands.handle_commands(["app.py", *flags], [], str(json_path), backup_dir, str(tmp_path / "src"))
        return calls[-1]

    return run, backup_dir, str(json_path)


@pytest.mark.parametrize("flags", [
    ("--edit", "--backup", "--editor=nano"),
    ("--edit", "--editor=nano", "--backup"),
    ("--editor=nano", "--backup", "--edit"),
])
def test_edit_with_backup_and_editor_in_any_order(setup, flags):
    run, backup_dir, json_path = setup
    args = run(*flags)
    assert args == ["nano", json_path]
    assert len(list_backups(backup_dir)) == 1


def test_edit_without_backup_flag_makes_no_backup(setup):
    run, backup_dir, json_path = setup
    run("--edit", "--editor=nano")
    assert list_backups(backup_dir) == []


def test_edit_uses_editor_env_var(setup, monkeypatch):
    run, _, json_path = setup
    monkeypatch.setenv("EDITOR", "emacs")
    assert run("--edit") == ["emacs", json_path]
