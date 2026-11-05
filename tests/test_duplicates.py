import os
import stat
import subprocess
import sys

import pyotp
import pytest
import shutil

from utils.utils import fzf_args

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))

ACCOUNTS = [
    {"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP"},
    {"issuer": "Work", "name": "me", "secret": "GEZDGNBVGY3TQOJQ"},
    {"issuer": "Work", "name": "me", "secret": "MFRGGZDFMZTWQ2LK"},
]


def make_copy(tmp_path):
    """Copy of the app with a fake fzf that picks a given line and runs the preview."""
    import json
    import shutil

    root = tmp_path / "app"
    shutil.copytree(SRC, root / "src")
    (root / "json").mkdir()
    (root / "json" / "secrets.json").write_text(json.dumps(ACCOUNTS))
    (root / "env" / "bin").mkdir(parents=True)
    # a wrapper, not a symlink: a symlinked venv python loses its packages
    python = root / "env" / "bin" / "python"
    python.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    python.chmod(python.stat().st_mode | stat.S_IEXEC)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_fzf = bin_dir / "fzf"
    # Picks line $PICK (0-based) of stdin; writes the preview of that line to $PREVIEW_OUT.
    fake_fzf.write_text(f"""#!{sys.executable}
import os, subprocess, sys
args = sys.argv[1:]
lines = sys.stdin.read().splitlines()
line = lines[int(os.environ["PICK"])]
preview = args[args.index("--preview") + 1]
delim = next(a.split("=", 1)[1] for a in args if a.startswith("--delimiter="))
field1 = line.split(delim)[0]
cmd = preview.replace("{{1}}", "'" + field1 + "'")
out = subprocess.run(cmd, shell=True, capture_output=True, text=True)
open(os.environ["PREVIEW_OUT"], "w").write(out.stdout + out.stderr)
print(line)
""")
    fake_fzf.chmod(fake_fzf.stat().st_mode | stat.S_IEXEC)
    return root, bin_dir


def test_selecting_second_duplicate_uses_its_own_secret(tmp_path):
    root, bin_dir = make_copy(tmp_path)
    preview_out = tmp_path / "preview.txt"
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
               PICK="1", PREVIEW_OUT=str(preview_out))

    result = subprocess.run(
        [sys.executable, str(root / "src" / "app.py"), "work"],
        capture_output=True, text=True, env=env,
    )

    expected = pyotp.TOTP(ACCOUNTS[2]["secret"]).now()
    other = pyotp.TOTP(ACCOUNTS[1]["secret"]).now()
    assert expected != other
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"OTP code for Work (me): {expected}" in result.stdout
    assert expected in preview_out.read_text()


@pytest.mark.skipif(shutil.which("fzf") is None, reason="fzf not installed")
@pytest.mark.parametrize("query, expected", [
    ("work", ["1\tWork (me)", "2\tWork (me)"]),
    ("git", ["0\tGitHub (me)"]),
    ("2", []),  # the hidden index must not be searchable
])
def test_real_fzf_searches_labels_and_returns_index(query, expected):
    args = [a for a in fzf_args("python", "preview.py") if not a.startswith("--preview")]
    args.remove("python preview.py {1}")
    lines = "0\tGitHub (me)\n1\tWork (me)\n2\tWork (me)\n"
    result = subprocess.run(args + [f"--filter={query}"], input=lines, capture_output=True, text=True)
    assert result.stdout.splitlines() == expected
