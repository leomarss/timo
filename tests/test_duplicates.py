"""End to end: real app process, fake fzf that runs the real preview script."""
import json
import os
import shutil
import stat
import subprocess
import sys

import pyotp
import pytest

from timo import preview
from timo.utils import fzf_args, preview_codes
from timo.vault import Vault

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
PASSPHRASE = "e2e passphrase"

ACCOUNTS = [
    {"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP"},
    {"issuer": "Work", "name": "me", "secret": "GEZDGNBVGY3TQOJQ"},
    {"issuer": "Work", "name": "me", "secret": "MFRGGZDFMZTWQ2LK"},
]

# Picks line $PICK (0-based), runs the preview command for it, and records
# the preview output plus the environment fzf was started with.
FAKE_FZF = """#!{python}
import json, os, subprocess, sys
args = sys.argv[1:]
lines = sys.stdin.read().splitlines()
line = lines[int(os.environ["PICK"])]
preview = args[args.index("--preview") + 1]
delim = next(a.split("=", 1)[1] for a in args if a.startswith("--delimiter="))
cmd = preview.replace("{{1}}", "'" + line.split(delim)[0] + "'")
out = subprocess.run(cmd, shell=True, capture_output=True, text=True)
json.dump({{"preview": out.stdout + out.stderr, "env": dict(os.environ)}}, open(os.environ["RECORD"], "w"))
print(line)
"""


@pytest.fixture
def app(tmp_path):
    home = tmp_path / "config"
    Vault(str(home / "secrets.enc"), PASSPHRASE).save(ACCOUNTS)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fzf = bin_dir / "fzf"
    fzf.write_text(FAKE_FZF.format(python=sys.executable))
    fzf.chmod(fzf.stat().st_mode | stat.S_IEXEC)
    record = tmp_path / "record.json"
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
               TIMO_HOME=str(home), TIMO_PASSPHRASE=PASSPHRASE, RECORD=str(record))

    def run(*argv, pick):
        result = subprocess.run([sys.executable, os.path.join(SRC, "app.py"), *argv],
                                capture_output=True, text=True, env=dict(env, PICK=str(pick)))
        return result, json.loads(record.read_text())

    return run


def test_selecting_second_duplicate_uses_its_own_secret(app):
    result, record = app("work", "--no-copy", pick=1)

    expected = pyotp.TOTP(ACCOUNTS[2]["secret"]).now()
    assert expected != pyotp.TOTP(ACCOUNTS[1]["secret"]).now()
    assert result.returncode == 0, result.stdout + result.stderr
    label, line = result.stdout.splitlines()
    assert label == "Work (me)" and line.split()[0] == expected
    assert f"{expected[:3]} {expected[3:]}" in record["preview"]


def test_fzf_and_preview_never_see_passphrase_or_secrets(app):
    _, record = app("work", "--no-copy", pick=0)
    env_dump = json.dumps(record["env"])
    assert "TIMO_PASSPHRASE" not in record["env"]
    assert PASSPHRASE not in env_dump
    for acc in ACCOUNTS:
        assert acc["secret"] not in env_dump
    assert "TIMO_PREVIEW" in record["env"]


# --- preview script ---------------------------------------------------------------

def test_preview_picks_code_for_current_window():
    data = preview_codes([(5, ACCOUNTS[0])], now=1000)
    env = {"TIMO_PREVIEW": json.dumps(data)}
    totp = pyotp.TOTP(ACCOUNTS[0]["secret"])
    for now in (1000, 1031, 1500):
        out = preview.main(["preview.py", "5"], env, now)
        code = totp.at(now)
        assert f"{code[:3]} {code[3:]}" in out
    assert "Expires in:" in preview.main(["preview.py", "5"], env, 1000)


def test_preview_after_codes_run_out():
    data = preview_codes([(0, ACCOUNTS[0])], now=1000)
    env = {"TIMO_PREVIEW": json.dumps(data)}
    assert "expired" in preview.main(["preview.py", "0"], env, 1000 + 20 * 30 + 1)


@pytest.mark.parametrize("argv, env", [(["p"], {}), (["p", "9"], None), (["p", "0"], {"TIMO_PREVIEW": "junk"})])
def test_preview_handles_missing_data(argv, env):
    if env is None:
        env = {"TIMO_PREVIEW": json.dumps(preview_codes([(0, ACCOUNTS[0])], now=0))}
    assert preview.main(argv, env, 0) == ""


# --- real fzf ---------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("fzf") is None, reason="fzf not installed")
@pytest.mark.parametrize("query, expected", [
    ("work", ["1\tWork (me)", "2\tWork (me)"]),
    ("git", ["0\tGitHub (me)"]),
    ("2", []),  # the hidden index must not be searchable
])
def test_real_fzf_searches_labels_and_returns_index(query, expected):
    args = fzf_args("python", "preview.py")
    i = args.index("--preview")
    del args[i:i + 2]
    lines = "0\tGitHub (me)\n1\tWork (me)\n2\tWork (me)\n"
    result = subprocess.run(args + [f"--filter={query}"], input=lines, capture_output=True, text=True)
    assert result.stdout.splitlines() == expected


def test_preview_command_survives_spaces_in_paths(tmp_path):
    folder = tmp_path / "Application Support"
    folder.mkdir()
    script = folder / "preview.py"
    script.write_text("import sys; print('ok', sys.argv[1])")
    preview = fzf_args(sys.executable, str(script))
    cmd = preview[preview.index("--preview") + 1].replace("{1}", "'3'")
    out = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    assert out.stdout == "ok 3\n", out.stderr
