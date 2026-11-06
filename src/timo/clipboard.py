"""Copy codes to the clipboard and clear them again after a delay.

Clearing runs in a small detached process (this file, run as a script), so
timo itself exits immediately. The code is passed on stdin rather than the
command line, where other users could see it with ps. The clipboard is only
cleared if it still holds the code, so anything copied since is left alone.
"""
import os
import subprocess
import sys
import time

DEFAULT_CLEAR_AFTER = 45  # seconds, same default as the `pass` password manager
CLEAR_AFTER_ENV = "TIMO_CLEAR_AFTER"


def copy(text):
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def schedule_clear(code, seconds):
    try:
        proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), str(seconds)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # survives timo exiting and Ctrl-C in the terminal
            close_fds=True,
        )
        proc.stdin.write(code.encode())
        proc.stdin.close()
        return True
    except Exception:
        return False


def clear_if_unchanged(code, seconds, paste, copy, sleep=time.sleep):
    sleep(seconds)
    try:
        if paste() == code:
            copy("")
    except Exception:
        pass


if __name__ == "__main__":
    code = sys.stdin.read()
    import pyperclip
    clear_if_unchanged(code, float(sys.argv[1]), pyperclip.paste, pyperclip.copy)
