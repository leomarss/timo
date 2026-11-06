import os
import sys

import pytest
import segno

from timo import qr, ui
from timo.otpauth import parse_otpauth_uri, to_otpauth_uri

SECRET = "JBSWY3DPEHPK3PXP"
OTHER = "GEZDGNBVGY3TQOJQ"

GITHUB = {"issuer": "GitHub", "name": "me@x.com", "secret": SECRET, "algorithm": "SHA1", "digits": 6,
          "date_added": "2026-11-05T10:00:00+01:00"}
AWS = {"issuer": "AWS", "name": "root", "secret": OTHER, "algorithm": "SHA256", "digits": 8}


def undated(acc):
    return {k: v for k, v in acc.items() if k != "date_added"}


# --- otpauth:// links --------------------------------------------------------------

def test_link_leaves_out_defaults():
    assert to_otpauth_uri(GITHUB) == f"otpauth://totp/GitHub:me%40x.com?secret={SECRET}&issuer=GitHub"


def test_link_keeps_algorithm_and_digits():
    assert to_otpauth_uri(AWS) == f"otpauth://totp/AWS:root?secret={OTHER}&issuer=AWS&algorithm=SHA256&digits=8"


@pytest.mark.parametrize("issuer, name", [
    ("GitHub", "me@x.com"),
    ("ACME Co", "john doe"),
    ("A&B=C", "x+y?z#w"),
    ("Zürich Bank", "ünïcode"),
    ("Odd:Issuer", "me"),
    ("Issuer", "name:with:colons"),
    ("", "only-a-name"),
])
def test_link_round_trips(issuer, name):
    acc = {"issuer": issuer, "name": name, "secret": SECRET, "algorithm": "SHA512", "digits": 8}
    assert parse_otpauth_uri(to_otpauth_uri(acc)) == acc


# --- QR codes in the terminal ------------------------------------------------------

HALF_BLOCKS = {" ": (False, False), "▀": (True, False), "▄": (False, True), "█": (True, True)}


def test_qr_lines_draw_the_qr_matrix():
    text = to_otpauth_uri(GITHUB)
    lines = qr.terminal_lines(text)
    drawn = []
    for line in lines:
        cells = [HALF_BLOCKS[c] for c in ui._ANSI.sub("", line)]
        drawn.append([top for top, _ in cells])
        drawn.append([bottom for _, bottom in cells])
    matrix = [[bool(m) for m in row]
              for row in segno.make_qr(text).matrix_iter(scale=1, border=qr.QUIET_ZONE)]
    assert drawn[:len(matrix)] == matrix
    assert not any(any(row) for row in drawn[len(matrix):])  # padding row is light


def test_qr_is_dark_on_light_whatever_the_terminal_colours():
    for line in qr.terminal_lines("hello"):
        assert line.startswith(qr.DARK_ON_LIGHT) and line.endswith(ui.RESET)


# --- the command -------------------------------------------------------------------

@pytest.fixture
def stored(cli):
    cli.store([GITHUB, AWS])
    return cli


@pytest.fixture
def terminal(monkeypatch):
    """stdout is a terminal (stdin stays a pipe, so questions read answers via input())."""
    monkeypatch.setattr(ui, "is_terminal", lambda stream=None: (stream or sys.stdout) is sys.stdout)


def test_piped_export_prints_one_link_per_account(stored):
    code, out, err = stored.run("--export")
    assert code == 0, err
    assert [parse_otpauth_uri(line) for line in out.splitlines()] == [undated(GITHUB), AWS]


def test_search_words_pick_what_is_exported(stored):
    code, out, _ = stored.run("--export", "git")
    assert code == 0
    assert out.splitlines() == [to_otpauth_uri(GITHUB)]


def test_no_match(stored):
    code, out, err = stored.run("--export", "nothing")
    assert code == 1
    assert out == ""
    assert 'No account matches "nothing"' in err


def test_output_file_is_private(stored, tmp_path):
    path = tmp_path / "accounts.txt"
    code, out, err = stored.run("--export", "--output", str(path))
    assert code == 0, err
    assert path.read_text().splitlines() == [to_otpauth_uri(GITHUB), to_otpauth_uri(AWS)]
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert "Exported 2 accounts" in out
    assert "isn't encrypted" in err


def test_output_never_overwrites(stored, tmp_path):
    path = tmp_path / "accounts.txt"
    path.write_text("keep me")
    code, _, err = stored.run("--export", "--output", str(path))
    assert code == 1
    assert "already exists" in err
    assert path.read_text() == "keep me"


def test_output_folder_must_exist(stored, tmp_path):
    path = tmp_path / "missing" / "accounts.txt"
    code, _, err = stored.run("--export", "--output", str(path))
    assert code == 1
    assert "Folder not found" in err
    assert not path.parent.exists()


def test_setup_qr_needs_a_terminal(stored):
    code, out, err = stored.run("--export", "--format", "setup-qr")
    assert code == 1
    assert out == ""
    assert "--format uri" in err


def test_links_on_a_terminal_ask_first(stored, terminal):
    code, out, err = stored.run("--export", "--format", "uri", answers=["n"])
    assert code == 0
    assert SECRET not in out
    assert "Nothing exported" in err

    code, out, _ = stored.run("--export", "--format", "uri", answers=["y"])
    assert code == 0
    assert to_otpauth_uri(GITHUB) in out and to_otpauth_uri(AWS) in out


def test_terminal_shows_setup_qr_codes_one_at_a_time(stored, terminal):
    code, out, err = stored.run("--export", answers=["y", ""])
    assert code == 0, err
    assert "GitHub (me@x.com) · 1 of 2" in out
    assert "AWS (root) · 2 of 2" in out
    assert out.count(qr.DARK_ON_LIGHT) > 10
    assert SECRET not in out  # only inside the QR code
    assert "\033[?1049h" in out and out.rstrip().endswith("Showed 2 accounts as QR codes")


def test_setup_qr_codes_can_stop_early(stored, terminal):
    code, out, _ = stored.run("--export", answers=["n"])
    assert code == 0
    assert "AWS (root)" not in out
    assert "Showed 1 of 2 accounts as QR codes" in out


def test_setup_qr_screen_is_left_on_ctrl_c(stored, terminal, monkeypatch):
    def interrupt(*_, **__):
        raise KeyboardInterrupt
    monkeypatch.setattr(ui, "confirm", interrupt)
    code, out, _ = stored.run("--export")
    assert code == 130
    assert out.index("\033[?1049h") < out.index("\033[?1049l")


@pytest.mark.parametrize("argv, error", [
    (["--export", "--format", "setup-qr", "--output", "x.txt"], "--output only works with --format uri"),
    (["--list", "--format", "uri"], "--format and --output only work with --export"),
    (["--output", "x.txt"], "--format and --output only work with --export"),
    (["--export", "--format", "csv"], "invalid choice"),
    (["--export", "--no-copy"], "--no-copy and --clear-after only apply"),
])
def test_bad_combinations(cli, capsys, argv, error):
    with pytest.raises(SystemExit) as exc:
        cli.run(*argv)
    assert exc.value.code == 2
    assert error in capsys.readouterr().err
