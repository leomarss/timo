"""Crash-safe writes for files only the current user may read.

Data goes to a temporary file in the same folder, is flushed to disk with
fsync, and only then takes the final name. A crash or full disk leaves either
the old file or the new one, never a half-written one, and no temp files.
"""
import os
import tempfile


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _fsync_dir(directory):
    # makes the rename itself durable; not supported everywhere, so best effort
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _write_temp(directory, data):
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-")  # created 0600
    try:
        _write_all(fd, data)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        os.remove(tmp_path)
        raise
    os.close(fd)
    return tmp_path


def write_private(path, data):
    """Atomically create or replace path with data (mode 0600, folder 0700)."""
    directory = os.path.dirname(os.path.abspath(path))
    tmp_path = _write_temp(directory, data)
    try:
        os.replace(tmp_path, path)
    except BaseException:
        os.remove(tmp_path)
        raise
    _fsync_dir(directory)


def write_new_private(path, data):
    """Like write_private, but raise FileExistsError instead of replacing an existing file."""
    directory = os.path.dirname(os.path.abspath(path))
    tmp_path = _write_temp(directory, data)
    try:
        os.link(tmp_path, path)  # atomic, and fails if path already exists
    finally:
        os.remove(tmp_path)
    _fsync_dir(directory)
