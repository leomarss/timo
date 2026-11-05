import io
import pathlib
import re
import types

import pytest

from totp_cli import messages, ui

PACKAGE = pathlib.Path(ui.__file__).parent


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def streams(monkeypatch):
    out, err = FakeTTY(), FakeTTY()
    # pytest re-captures sys.stdout around each test, so swap the sys ui sees
    monkeypatch.setattr(ui, "sys", types.SimpleNamespace(stdout=out, stderr=err))
    monkeypatch.delenv("NO_COLOR", raising=False)
    return out, err


def test_symbols_and_streams(streams):
    out, err = streams
    ui.ok("Backup saved", "~/x")
    ui.warn("Careful")
    ui.error("Broken", "Try this")
    ui.note("FYI")
    assert "✓" in out.getvalue() and "Backup saved" in out.getvalue()
    assert "✗" not in out.getvalue() and "!" not in out.getvalue()
    assert "Careful" in err.getvalue() and "Broken" in err.getvalue() and "FYI" in err.getvalue()
    assert "  Try this" in err.getvalue()


def test_colour_on_a_terminal(streams):
    out, err = streams
    ui.ok("Done")
    ui.error("Broken")
    assert ui.GREEN in out.getvalue()
    assert ui.RED in err.getvalue()


def test_no_colour_when_piped(capsys, monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    ui.ok("Done", "detail")
    ui.error("Broken", "hint")
    out, err = capsys.readouterr()
    assert out == "✓ Done  detail\n"
    assert err == "✗ Broken\n  hint\n"


def test_no_colour_with_NO_COLOR(streams, monkeypatch):
    out, err = streams
    monkeypatch.setenv("NO_COLOR", "1")
    ui.ok("Done")
    ui.warn("Careful")
    assert "\033" not in out.getvalue() + err.getvalue()


@pytest.mark.parametrize("count, expected", [(0, "0 accounts"), (1, "1 account"), (2, "2 accounts")])
def test_plural(count, expected):
    assert ui.plural(count, "account") == expected


@pytest.mark.parametrize("seconds, color", [(30, ui.GREEN), (21, ui.GREEN), (15, ui.YELLOW), (5, ui.RED)])
def test_time_color(seconds, color):
    assert ui.time_color(seconds) == color


# --- the message catalogue ------------------------------------------------------------

MESSAGES = {k: v for k, v in vars(messages).items() if k.isupper()}
SOURCE = "\n".join(p.read_text() for p in PACKAGE.rglob("*.py") if p.name != "messages.py")


@pytest.mark.parametrize("name", sorted(MESSAGES))
def test_every_message_is_used(name):
    assert re.search(rf"\bmsg\.{name}\b", SOURCE), f"{name} isn't used anywhere"


@pytest.mark.parametrize("name", sorted(k for k in MESSAGES
                                         if not k.startswith("PROMPT_") and isinstance(MESSAGES[k], str)))
def test_messages_have_no_full_stop(name):
    assert not MESSAGES[name].endswith("."), name


def test_no_stray_prints_in_commands():
    for name in ("commands.py", "cli.py", "utils.py"):
        text = (PACKAGE / name).read_text()
        assert not re.search(r"^\s*print\((?!file=sys\.stderr\))", text, re.M), name


# --- boxes, tables, codes, ages --------------------------------------------------------

@pytest.mark.parametrize("code, shown", [("482913", "482 913"), ("48291305", "4829 1305")])
def test_group_code(code, shown):
    assert ui.group_code(code) == shown


@pytest.mark.parametrize("seconds, expected", [
    (5, "just now"), (60, "1 minute"), (150, "2 minutes"), (2 * 3600, "2 hours"),
    (86400, "1 day"), (4 * 86400, "4 days"), (21 * 86400, "3 weeks"), (400 * 86400, "1 year"),
])
def test_age(seconds, expected):
    assert ui.age(seconds) == expected


def test_box_lines_up_with_colour(streams):
    out, _ = streams
    ui.box([ui.paint("482 913", ui.BOLD, ui.GREEN) + "   17s left"], title=ui.paint("GitHub (me)", ui.BOLD))
    lines = [ui._ANSI.sub("", line) for line in out.getvalue().splitlines()]
    assert lines[0].startswith("╭─ GitHub (me) ") and lines[0].endswith("╮")
    assert lines[1] == "│  482 913   17s left  │"
    assert lines[2].startswith("╰") and lines[2].endswith("╯")
    assert len({len(line) for line in lines}) == 1


def test_error_with_hints_is_a_box_on_a_terminal(streams):
    _, err = streams
    ui.error("Several accounts match", "Or narrow the search:")
    text = ui._ANSI.sub("", err.getvalue())
    assert text.startswith("╭─ ✗ Several accounts match") and "│  Or narrow the search:" in text


@pytest.fixture
def terminal(cli, monkeypatch):
    """Run the cli as if stdout and stderr were a terminal (without colour, for easy matching)."""
    out, err = FakeTTY(), FakeTTY()
    monkeypatch.setattr(ui, "sys", types.SimpleNamespace(stdout=out, stderr=err))
    monkeypatch.setenv("NO_COLOR", "1")

    def run(*argv):
        out.seek(0), out.truncate(), err.seek(0), err.truncate()
        cli.run(*argv)
        return out.getvalue(), err.getvalue()
    return run


ACC = [{"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP"}]


def test_get_draws_a_box_with_grouped_code(cli, terminal):
    cli.store(ACC)
    out, _ = terminal("git", "--no-copy")
    top, row, bottom = out.splitlines()
    assert top.startswith("╭─ GitHub (me) ")
    assert re.match(r"│  \d{3} \d{3}   \d+s left · not copied +│", row)


def test_list_backups_shows_ages(cli, terminal):
    cli.store(ACC)
    cli.run("--backup")
    out, _ = terminal("--list-backups")
    header, rule, row = out.splitlines()
    assert header.split() == ["Backup", "Age"]
    assert row.split()[0].startswith("secrets.enc.bak.") and row.split()[1] == "just"


def test_list_shows_when_accounts_were_added(cli, terminal):
    cli.store([
        {"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP", "date_added": "2026-11-05T16:02:11+01:00"},
        {"issuer": "AWS", "name": "ops", "secret": "GEZDGNBVGY3TQOJQ"},  # from before date_added
    ])
    out, _ = terminal("--list")
    header, rule, first, second = out.splitlines()
    assert header.split() == ["#", "Issuer", "Account", "Added"]
    assert first.split() == ["1", "GitHub", "me", "2026-11-05"]
    assert second.split() == ["2", "AWS", "ops", "-"]


def test_list_piped_stays_one_label_per_line(cli):
    cli.store([{"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP", "date_added": "2026-11-05T16:02:11+01:00"}])
    _, out, _ = cli.run("--list")
    assert out == "GitHub (me)\n"
