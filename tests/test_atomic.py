import os

import pytest

from timo import fileio
from timo.utils import BACKUP_PREFIX, create_backup, list_backups


def listing(path):
    return sorted(p.name for p in path.iterdir())


# --- write_private -----------------------------------------------------------------

def test_write_private_creates_file_and_private_dir(tmp_path):
    target = tmp_path / "cfg" / "secrets.enc"
    fileio.write_private(str(target), b"data")
    assert target.read_bytes() == b"data"
    assert os.stat(target).st_mode & 0o777 == 0o600
    assert os.stat(target.parent).st_mode & 0o777 == 0o700


def test_write_private_fsyncs_before_replacing(tmp_path, monkeypatch):
    events = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(fileio.os, "fsync", lambda fd: (events.append("fsync"), real_fsync(fd)))
    monkeypatch.setattr(fileio.os, "replace", lambda a, b: (events.append("replace"), real_replace(a, b)))
    fileio.write_private(str(tmp_path / "f"), b"data")
    assert events.index("fsync") < events.index("replace")


@pytest.mark.parametrize("fail_at", ["write", "fsync", "replace"])
def test_failed_write_keeps_old_file_and_leaves_no_temp(tmp_path, monkeypatch, fail_at):
    target = tmp_path / "secrets.enc"
    target.write_bytes(b"old")

    def boom(*a, **k):
        raise OSError("disk full")

    if fail_at == "write":
        monkeypatch.setattr(fileio, "_write_all", boom)
    else:
        monkeypatch.setattr(fileio.os, fail_at, boom)

    with pytest.raises(OSError):
        fileio.write_private(str(target), b"new")
    assert target.read_bytes() == b"old"
    assert listing(tmp_path) == ["secrets.enc"]


# --- write_new_private (never overwrites) -------------------------------------------

def test_write_new_private_refuses_to_overwrite(tmp_path):
    target = tmp_path / "f"
    target.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        fileio.write_new_private(str(target), b"other")
    assert target.read_bytes() == b"keep"
    assert listing(tmp_path) == ["f"]


def test_write_new_private_failure_leaves_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(fileio, "_write_all", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        fileio.write_new_private(str(tmp_path / "f"), b"data")
    assert listing(tmp_path) == []


# --- backups ---------------------------------------------------------------------

def test_failed_backup_leaves_no_partial_backup(tmp_path, monkeypatch):
    src = tmp_path / "secrets.enc"
    src.write_bytes(b"x" * 10000)
    backups = tmp_path / "backups"
    monkeypatch.setattr(fileio, "_write_all", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        create_backup(str(src), str(backups))
    assert list_backups(str(backups)) == []
    assert listing(backups) == []


def test_backup_is_private_copy(tmp_path):
    src = tmp_path / "secrets.enc"
    src.write_bytes(b"content")
    path = create_backup(str(src), str(tmp_path / "backups"))
    assert open(path, "rb").read() == b"content"
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert os.path.basename(path).startswith(BACKUP_PREFIX)


def test_backup_never_overwrites_even_if_name_appears_late(tmp_path, monkeypatch):
    """Another backup taking the same name between check and write must not be clobbered."""
    src = tmp_path / "secrets.enc"
    src.write_bytes(b"mine")
    backups = tmp_path / "backups"
    backups.mkdir()
    real = fileio.write_new_private
    calls = []

    def racing(path, data):
        if not calls:  # someone else grabs the first name just before we write it
            open(path, "wb").write(b"theirs")
        calls.append(path)
        return real(path, data)

    monkeypatch.setattr(fileio, "write_new_private", racing)
    path = create_backup(str(src), str(backups))
    assert open(path, "rb").read() == b"mine"
    assert open(calls[0], "rb").read() == b"theirs"
    assert path != calls[0]


# --- restore into an empty store ---------------------------------------------------

def test_restore_into_empty_store_is_private(cli):
    cli.store([{"issuer": "A", "name": "a", "secret": "JBSWY3DPEHPK3PXP"}])
    cli.run("--backup")
    name = list_backups(str(cli.backups))[0]
    cli.secrets.unlink()
    code, out, _ = cli.run("--restore", name)
    assert code == 0
    assert os.stat(cli.secrets).st_mode & 0o777 == 0o600
    assert cli.load()[0]["issuer"] == "A"
