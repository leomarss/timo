import os

import pytest

from utils.utils import resolve_backup_path, restore_backup


@pytest.fixture
def backup_dir(tmp_path):
    d = tmp_path / "backups"
    d.mkdir()
    (d / "secrets.json.bak.2025-01-01_00-00-00").write_text("[]")
    return str(d)


def test_resolves_valid_backup_name(backup_dir):
    name = "secrets.json.bak.2025-01-01_00-00-00"
    assert resolve_backup_path(backup_dir, name) == os.path.join(os.path.realpath(backup_dir), name)


@pytest.mark.parametrize("name", [
    "../secrets.json",
    "../../etc/passwd",
    "/etc/passwd",
    "secrets.json.bak.x/../../evil",
    "notabackup.txt",
    "",
])
def test_rejects_paths_outside_backup_dir_or_bad_names(backup_dir, name):
    with pytest.raises(ValueError):
        resolve_backup_path(backup_dir, name)


def test_restore_rejects_traversal(backup_dir, tmp_path):
    target = tmp_path / "secrets.json"
    target.write_text('[{"keep": true}]')
    with pytest.raises(ValueError):
        restore_backup("../../etc/passwd", backup_dir, str(target))
    assert target.read_text() == '[{"keep": true}]'
