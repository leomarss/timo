"""ui.ask(): the current value comes typed in on a terminal, ready to change."""
import io
import os
import pty
import subprocess
import sys
import time

import pytest

from timo import ui
from test_hidden_input import SRC, _read_until

CHILD = """
import sys
sys.path.insert(0, sys.argv[1])
from timo import ui
value = ui.ask("Name", sys.argv[3])
with open(sys.argv[2], "w") as f:
    f.write(value)
"""

LEFT, RIGHT, HOME, END, DELETE = "\x1b[D", "\x1b[C", "\x1b[H", "\x1b[F", "\x1b[3~"


def ask_in_pty(current, typed, result_file, timeout=10):
    """Run ui.ask in a fresh Python on a real pseudo-terminal; returns what it showed."""
    fd, child_end = pty.openpty()
    child = subprocess.Popen(
        [sys.executable, "-c", CHILD, SRC, str(result_file), current],
        stdin=child_end, stdout=child_end, stderr=child_end, start_new_session=True,
    )
    os.close(child_end)
    deadline = time.monotonic() + timeout
    try:
        output = _read_until(fd, lambda out: b"Name: " in out, deadline)
        for key in typed:  # one key at a time, like a person
            os.write(fd, key.encode())
            time.sleep(0.02)
        output += _read_until(fd, lambda out: False, deadline)
    finally:
        child.kill()
        child.wait()
        os.close(fd)
    return output.decode(errors="replace")


@pytest.mark.parametrize("current, typed, expected", [
    ("me", ["\r"], "me"),  # Enter keeps it
    ("me", ["\x7f", "\x7f", *"work", "\r"], "work"),  # backspace over it
    ("me", ["\x15", *"work", "\r"], "work"),  # Ctrl-U clears it
    ("me", ["\x15", "\r"], "me"),  # cleared and nothing typed: kept
    ("leo@wrok", [LEFT, LEFT, LEFT, DELETE, RIGHT, "r", "\r"], "leo@work"),  # fix a typo mid-word
    ("ops", [HOME, *"dev", END, "!", "\r"], "devops!"),
    ("ops", ["\x01", "x", "\x05", "y", "\r"], "xopsy"),  # Ctrl-A / Ctrl-E
    ("abc", [HOME, DELETE, RIGHT, DELETE, "\r"], "b"),
    ("me", [*"é", "\r"], "meé"),  # non-ASCII
])
def test_editing_the_typed_in_value(tmp_path, current, typed, expected):
    result_file = tmp_path / "result"
    output = ask_in_pty(current, typed, result_file)
    assert f"Name: {current}" in output
    assert result_file.read_text() == expected


def test_without_a_terminal_the_value_is_in_brackets(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("\nwork\n"))
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or sys.stdin.readline())
    assert ui.ask("Name", "me") == "me"
    assert ui.ask("Name", "me") == "work"
    assert prompts == ["Name [me]: ", "Name [me]: "]
