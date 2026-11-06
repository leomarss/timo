import io
import os
import pty
import select
import signal
import sys
import time

from timo.utils import read_hidden

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
LONG_SECRET = "otpauth-migration://offline?data=" + "A" * 3000


CHILD = """
import os, sys
sys.path.insert(0, sys.argv[1])
from timo.utils import read_hidden
value = read_hidden("Paste: ")
with open(sys.argv[2], "w") as f:
    f.write(value)
"""


def _read_until(fd, done, deadline):
    output = b""
    while not done(output):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            break
        try:
            chunk = os.read(fd, 4096)
        except OSError:  # child closed the terminal
            break
        if not chunk:
            break
        output += chunk
    return output


def run_in_pty(typed, result_file, timeout=10):
    """Run read_hidden in a fresh Python attached to a real pseudo-terminal."""
    pid, fd = pty.fork()
    if pid == 0:
        os.execv(sys.executable, [sys.executable, "-c", CHILD, SRC, str(result_file)])

    deadline = time.monotonic() + timeout
    try:
        # paste only once the prompt is shown, like a person would
        output = _read_until(fd, lambda out: b"Paste: " in out, deadline)
        os.write(fd, typed.encode())
        output += _read_until(fd, lambda out: False, deadline)
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(pid, 0)
        os.close(fd)
    return output.decode(errors="replace")


def test_tty_input_is_not_echoed_and_not_truncated(tmp_path):
    result_file = tmp_path / "result"
    output = run_in_pty(LONG_SECRET + "\n", result_file)

    assert result_file.read_text() == LONG_SECRET
    assert "Paste: " in output
    assert "AAAA" not in output


def test_tty_backspace_edits_input(tmp_path):
    result_file = tmp_path / "result"
    run_in_pty("abX\x7fc\n", result_file)

    assert result_file.read_text() == "abc"


def test_non_tty_reads_a_line(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("piped-value\nnext\n"))
    assert read_hidden("Paste: ") == "piped-value"
    assert "piped-value" not in capsys.readouterr().out
