import pathlib
import re
import types

import pytest

from timo import ui
from timo.cli import build_parser

README = pathlib.Path(__file__).parent.parent / "README.md"


class FakeTTY:
    def isatty(self):
        return True


def plain_help():
    return build_parser().format_help()


def test_every_option_is_in_the_help():
    parser = build_parser()
    listed = {action for _, entries in parser.sections for action, _, _ in entries}
    assert set(parser._actions) <= listed  # a flag added outside a section would go missing
    text = parser.format_help()
    for action in parser._actions:
        for flag in action.option_strings:
            assert re.search(rf"(^|[\s,]){re.escape(flag)}\b", text, re.M), flag


def test_descriptions_line_up():
    lines = [line for line in plain_help().splitlines() if line.startswith("  ")]
    columns = {re.search(r"\S\s{2,}(\S)", line).start(1) for line in lines}
    assert len(columns) == 1


def test_options_of_one_action_are_indented_under_it():
    lines = plain_help().splitlines()
    edit = lines.index(next(line for line in lines if line.startswith("  --edit ")))
    assert lines[edit + 1].startswith("      --backup ")
    assert lines[edit + 2].startswith("      --editor CMD ")
    words = lines.index(next(line for line in lines if line.startswith("  timo [WORDS...]")))
    assert lines[words + 1].startswith("      --no-copy ")


def test_sections_in_order():
    titles = [line for line in plain_help().splitlines() if line and not line.startswith(" ")]
    assert titles[1:7] == ["Copy a code", "See your accounts", "Add and change accounts",
                           "Backups", "Passphrase", "Other"]


def test_no_colour_when_piped():
    assert "\033[" not in plain_help()


def test_colour_on_a_terminal(monkeypatch):
    plain = plain_help()
    monkeypatch.setattr(ui, "sys", types.SimpleNamespace(stdout=FakeTTY(), stderr=FakeTTY()))
    monkeypatch.delenv("NO_COLOR", raising=False)
    text = build_parser().format_help()
    assert ui.CYAN + "--list" + ui.RESET in text
    assert ui.BOLD + "Backups" + ui.RESET in text
    assert ui._ANSI.sub("", text) == plain  # same layout, colour only


def test_fits_in_100_columns():
    assert max(len(line) for line in plain_help().splitlines()) <= 100


def test_readme_usage_matches_the_help():
    block = re.search(r"## 🧪 Usage\n\n```\n(.*?)```", README.read_text(), re.S).group(1)
    assert block == plain_help(), "README usage is out of date: paste the output of `timo --help | cat`"


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_flags_exit_cleanly(cli, capsys, flag):
    with pytest.raises(SystemExit) as exc:
        cli.run(flag)
    assert exc.value.code == 0
    assert capsys.readouterr().out == plain_help()
