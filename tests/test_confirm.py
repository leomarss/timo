import io
import os
import pty
import threading
import time
import types

import pytest

from timo import ui


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def keyboard(monkeypatch):
    """A real pseudo-terminal as stdin; press(keys) types them once confirm() is waiting."""
    master, slave = pty.openpty()
    stdin = open(slave, "rb", buffering=0)
    stdout = FakeTTY()
    monkeypatch.setattr(ui, "sys", types.SimpleNamespace(stdin=stdin, stdout=stdout, stderr=FakeTTY()))
    monkeypatch.setenv("NO_COLOR", "1")

    class Keyboard:
        out = stdout

        def ask(self, *keys, default=False, early=b""):
            os.write(master, early)  # typed before the question appeared

            def type_keys():
                time.sleep(0.15)  # after confirm() has flushed and started reading
                for key in keys:
                    os.write(master, key)
                    time.sleep(0.08)

            thread = threading.Thread(target=type_keys)
            thread.start()
            try:
                return ui.confirm("Remove it?", default=default)
            finally:
                thread.join()

    yield Keyboard()
    stdin.close()
    os.close(master)


@pytest.mark.parametrize("key, answer", [(b"y", True), (b"Y", True), (b"n", False), (b"N", False),
                                         (b"\x1b", False)])
def test_one_key_answers(keyboard, key, answer):
    assert keyboard.ask(key) is answer
    assert keyboard.out.getvalue() == f"Remove it? [y/N] {'yes' if answer else 'no'}\n"


@pytest.mark.parametrize("default, hint", [(False, "[y/N]"), (True, "[Y/n]")])
def test_enter_takes_the_default(keyboard, default, hint):
    assert keyboard.ask(b"\r", default=default) is default
    assert keyboard.out.getvalue().startswith(f"Remove it? {hint} ")


def test_other_keys_are_ignored_with_one_hint(keyboard):
    assert keyboard.ask(b"x", b"q", b"1", b"y") is True
    assert keyboard.out.getvalue() == "Remove it? [y/N] (press y or n) yes\n"


def test_arrow_key_is_not_esc(keyboard):
    assert keyboard.ask(b"\x1b[A", b"y") is True
    assert "(press y or n)" in keyboard.out.getvalue()


def test_keys_typed_before_the_question_are_dropped(keyboard):
    assert keyboard.ask(b"n", early=b"y") is False


def test_ctrl_d_stops(keyboard):
    with pytest.raises(EOFError):
        keyboard.ask(b"\x04")


# --- without a terminal: read a line ------------------------------------------------

@pytest.mark.parametrize("line, default, answer", [
    ("y", False, True), ("yes", False, True), ("Y", False, True),
    ("n", True, False), ("no", True, False),
    ("", False, False), ("", True, True),
])
def test_line_answers(monkeypatch, line, default, answer):
    monkeypatch.setattr("builtins.input", lambda prompt="": line)
    assert ui.confirm("Remove it?", default=default) is answer


def test_line_asks_again_after_another_answer(monkeypatch, capsys):
    replies = iter(["maybe", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(replies))
    assert ui.confirm("Remove it?") is True
    assert "(press y or n)" in capsys.readouterr().err
