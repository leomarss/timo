import pytest

from utils import commands


@pytest.fixture
def run(tmp_path, monkeypatch, capsys):
    json_path = tmp_path / "json" / "secrets.json"
    json_path.parent.mkdir()
    json_path.write_text("[]")
    backup_dir = str(tmp_path / "json" / "backups")  # deliberately not created

    def _run(*flags, accounts=(), answer="y"):
        monkeypatch.setattr("builtins.input", lambda prompt="": answer)
        with pytest.raises(SystemExit) as exc:
            commands.handle_commands(["app.py", *flags], list(accounts), str(json_path), backup_dir, str(tmp_path / "src"))
        return exc.value.code, capsys.readouterr().out

    return _run


def test_stats_with_no_accounts(run):
    code, out = run("--stats")
    assert code == 0
    assert "Total accounts: 0" in out


def test_stats_with_accounts(run):
    code, out = run("--stats", accounts=[
        {"issuer": "GitHub", "name": "a", "secret": "X"},
        {"issuer": "GitHub", "name": "b", "secret": "Y"},
        {"issuer": "AWS", "name": "c", "secret": "Z"},
    ])
    assert code == 0
    assert "Total accounts: 3" in out
    assert "GitHub -> 2" in out


def test_list_backups_without_backup_dir(run):
    code, out = run("--list-backups")
    assert code == 0
    assert "No backups found" in out


def test_remove_all_without_backup_dir(run):
    code, out = run("--backup", "--remove-all")
    assert code == 0
    assert "No backups to remove." in out


def test_restore_missing_backup(run):
    code, out = run("--restore", "secrets.json.bak.2000-01-01_00-00-00")
    assert code == 1
    assert "Backup not found" in out
