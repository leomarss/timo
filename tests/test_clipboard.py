import os
import subprocess
import sys
import time

import pytest

from timo import clipboard, commands

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
ACC = [{"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP"}]


class FakeClipboard:
    def __init__(self, content=""):
        self.content = content

    def paste(self):
        return self.content

    def copy(self, text):
        self.content = text


# --- the clearing rule -------------------------------------------------------------

def test_clears_when_code_is_still_there():
    board = FakeClipboard("123456")
    slept = []
    clipboard.clear_if_unchanged("123456", 45, board.paste, board.copy, slept.append)
    assert slept == [45]
    assert board.content == ""


def test_leaves_something_copied_later_alone():
    board = FakeClipboard("123456")
    clipboard.clear_if_unchanged("123456", 45, board.paste, board.copy,
                                 lambda s: board.copy("my own text"))
    assert board.content == "my own text"


def test_clipboard_errors_are_ignored():
    def broken():
        raise RuntimeError("no clipboard")
    clipboard.clear_if_unchanged("123456", 1, broken, broken, lambda s: None)


# --- how timo schedules it ---------------------------------------------------------

@pytest.fixture
def spawned(monkeypatch):
    """Capture the background clearer instead of starting it."""
    calls = []

    class FakePopen:
        def __init__(self, argv, **kwargs):
            self.argv, self.kwargs = argv, kwargs
            self.stdin = self
            self.written = b""
            calls.append(self)

        def write(self, data):
            self.written += data

        def close(self):
            pass

    monkeypatch.setattr(clipboard.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(clipboard, "copy", lambda code: True)
    monkeypatch.delenv("TIMO_CLEAR_AFTER", raising=False)
    return calls


def test_get_schedules_clear_with_code_on_stdin_not_argv(cli, spawned):
    cli.store(ACC)
    code, out, _ = cli.run("git")
    assert code == 0
    assert "· copied, clears in 45s" in out
    [proc] = spawned
    otp = out.splitlines()[1].split()[0]
    assert proc.written == otp.encode()
    assert otp not in " ".join(proc.argv)
    assert proc.argv[-1] == "45"
    assert proc.kwargs.get("start_new_session") is True


@pytest.mark.parametrize("argv, env, expected", [
    (["git", "--clear-after", "10"], None, "clears in 10s"),
    (["git"], "20", "clears in 20s"),
    (["git", "--clear-after", "5"], "20", "clears in 5s"),
])
def test_clear_delay_can_be_changed(cli, spawned, monkeypatch, argv, env, expected):
    if env:
        monkeypatch.setenv("TIMO_CLEAR_AFTER", env)
    cli.store(ACC)
    code, out, _ = cli.run(*argv)
    assert expected in out


@pytest.mark.parametrize("argv, env", [(["git", "--clear-after", "0"], None), (["git"], "0")])
def test_zero_disables_clearing(cli, spawned, monkeypatch, argv, env):
    if env:
        monkeypatch.setenv("TIMO_CLEAR_AFTER", env)
    cli.store(ACC)
    code, out, _ = cli.run(*argv)
    assert code == 0 and out.rstrip().endswith("· copied")
    assert spawned == []


def test_no_copy_schedules_nothing(cli, spawned):
    cli.store(ACC)
    cli.run("git", "--no-copy")
    assert spawned == []


def test_bad_clear_after_env_is_rejected(cli, spawned, monkeypatch):
    monkeypatch.setenv("TIMO_CLEAR_AFTER", "soon")
    cli.store(ACC)
    code, _, err = cli.run("git")
    assert code == 1 and "TIMO_CLEAR_AFTER" in err


# --- end to end with a real background process ----------------------------------------

def test_background_clear_end_to_end(tmp_path):
    """Real timo process and real detached clearer, with a fake pyperclip backed by a file."""
    board = tmp_path / "board.txt"
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "pyperclip.py").write_text(
        "import os\n"
        "P = os.environ['FAKE_BOARD']\n"
        "def copy(t): open(P, 'w').write(t)\n"
        "def paste(): return open(P).read() if os.path.exists(P) else ''\n"
    )
    from timo.vault import Vault
    Vault(str(tmp_path / "cfg" / "secrets.enc"), "e2e passphrase").save(ACC)
    env = dict(os.environ, PYTHONPATH=str(fake), FAKE_BOARD=str(board),
               TIMO_HOME=str(tmp_path / "cfg"), TIMO_PASSPHRASE="e2e passphrase")

    start = time.time()
    result = subprocess.run([sys.executable, os.path.join(SRC, "app.py"), "git", "--clear-after", "2"],
                            capture_output=True, text=True, env=env, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert time.time() - start < 2, "timo must not wait for the clear"
    otp = result.stdout.splitlines()[1].split()[0]
    assert board.read_text() == otp

    deadline = time.time() + 10
    while time.time() < deadline and board.read_text() != "":
        time.sleep(0.2)
    assert board.read_text() == ""
