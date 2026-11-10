"""Command-line entry point.

Every option starts with '-' or '--'; plain words are always a search, so an
account can be called "edit" or "list" without clashing with a command.
"""
import argparse
import os
import sys

from timo import __version__, commands, ui
from timo import messages as msg
from timo.commands import Abort, Context

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

INTRO = "timo · your authenticator app, in the terminal, one word away"
FOOTER = (
    "Secrets live in ~/.config/timo/ (set TIMO_HOME to use another folder).",
    "Set TIMO_CLEAR_AFTER to change the default of --clear-after.",
    'To search for a word that starts with "-": timo -- -word',
)

EXPORT_FORMATS = ("setup-qr", "uri")

# action name -> (flag, handler)
ACTIONS = {
    "list": ("--list", commands.cmd_list),
    "watch": ("--watch", commands.cmd_watch),
    "edit": ("--edit", commands.cmd_edit),
    "initialize": ("--initialize", commands.cmd_import),
    "export": ("--export", commands.cmd_export),
    "add": ("--add", commands.cmd_add),
    "passwd": ("--passwd", commands.cmd_passwd),
    "forget": ("--forget", commands.cmd_forget),
    "remember": ("--remember", commands.cmd_remember),
    "list-backups": ("--list-backups", commands.cmd_backup_list),
    "restore": ("--restore", commands.cmd_backup_restore),
    "remove": ("--remove", commands.cmd_remove),
    "remove-backups": ("--remove-backups", commands.cmd_backup_remove),
    "remove-all-backups": ("--remove-all-backups", commands.cmd_backup_remove_all),
    "backup": ("--backup", commands.cmd_backup_create),
    "get": (None, commands.cmd_get),
}


def config_dir():
    if os.environ.get("TIMO_HOME"):
        return os.environ["TIMO_HOME"]
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "timo")


def make_context():
    home = config_dir()
    return Context(
        secrets_path=os.path.join(home, "secrets.enc"),
        backup_dir=os.path.join(home, "backups"),
        python_path=sys.executable,
        preview_script=os.path.join(PACKAGE_DIR, "preview.py"),
    )


def _seconds(value):
    try:
        seconds = int(value)
    except ValueError:
        seconds = -1
    if seconds < 0:
        raise argparse.ArgumentTypeError("must be a whole number of seconds (0 = never clear)")
    return seconds


class Parser(argparse.ArgumentParser):
    """An ArgumentParser whose --help is grouped by task.

    The help is generated from the add_argument() calls: flag names and
    placeholders come from each action, descriptions from its help=. Only the
    section titles, INTRO and FOOTER are written by hand. Options that only
    work with one action are listed indented under it.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sections = []  # [(title, [(action, help, indented)])]

    def section(self, title):
        self.sections.append((title, []))

    def option(self, *flags, under=None, **kwargs):
        """add_argument(), and list it in the current section (indented if `under` an action)."""
        action = self.add_argument(*flags, **kwargs)
        self.sections[-1][1].append((action, action.help, under is not None))
        return action

    def format_help(self):
        rows = [(title, [(_invocation(action), text, indented) for action, text, indented in entries])
                for title, entries in self.sections]
        width = max(len(name) + len(meta) + (4 if indented else 0)
                    for _, entries in rows for (name, meta), _, indented in entries)
        lines = [ui.paint(INTRO, ui.BOLD), ""]
        for title, entries in rows:
            lines.append(ui.paint(title, ui.BOLD))
            for (name, meta), text, indented in entries:
                indent = "      " if indented else "  "
                gap = " " * (width - len(name) - len(meta) - len(indent) + 5)
                shown = ui.paint(name, ui.CYAN) + (ui.paint(meta, ui.DIM) if meta else "")
                lines.append(f"{indent}{shown}{gap}{text}")
            lines.append("")
        lines += [ui.paint(line, ui.DIM) for line in FOOTER]
        return "\n".join(lines) + "\n"


def _invocation(action):
    """("--restore", " NAME"): how an action is typed, split into name and placeholder."""
    if not action.option_strings:
        return "timo", f" [{action.metavar}...]"
    name = ", ".join(sorted(action.option_strings, key=len, reverse=True))
    if action.nargs == 0:
        return name, ""
    metavar = action.metavar or action.dest.upper()
    return name, f" {metavar}..." if action.nargs == "+" else f" {metavar}"


def build_parser():
    parser = Parser(
        prog="timo",
        usage="timo [WORDS...] [--no-copy] [--clear-after SECONDS]\n       timo --<action> [options]",
        add_help=False,  # -h is declared below, in its section
        allow_abbrev=False,  # flags must be spelled out: --lis is not --list
    )
    option = parser.option

    parser.section("Copy a code")
    words = option("query", nargs="*", metavar="WORDS",
                   help="copy the code of the account matching all words (none: pick with fzf)")
    option("--no-copy", action="store_true", under=words, help="print the code, don't copy it")
    option("--clear-after", type=_seconds, metavar="SECONDS", under=words,
           help="clear the clipboard after SECONDS, 0 = never (default 45)")

    parser.section("See your accounts")
    option("--list", action="store_true", help="list all accounts, the day each was added, and how many there are")
    option("--watch", action="store_true", help="show all codes, refreshing every second")

    parser.section("Add and change accounts")
    option("--initialize", action="store_true", help="import a Google Authenticator export")
    export = option("--export", action="store_true",
                    help="export accounts matching WORDS (none: all) to another app")
    option("--format", choices=EXPORT_FORMATS, metavar="FORMAT", under=export,
           help="setup-qr: one QR code per account (default in a terminal), or uri")
    option("--output", metavar="FILE", under=export, help="write otpauth:// links to FILE (readable only by you)")
    option("--add", action="store_true", help="add one account (setup QR code, otpauth:// link or secret key)")
    option("--remove", action="store_true", help="pick an account and remove it (asks first)")
    option("--edit", action="store_true",
           help="rename an account or fix its key (WORDS: pick among the matching ones)")

    parser.section("Backups")
    option("--backup", action="store_true", help="create a backup")
    option("--list-backups", action="store_true", help="show available backups")
    option("--restore", metavar="NAME", help="restore a backup (current secrets are backed up first)")
    option("--remove-backups", nargs="+", metavar="NAME", help="delete backups")
    option("--remove-all-backups", action="store_true", help="delete all backups (asks first)")

    parser.section("Passphrase")
    option("--passwd", action="store_true", help="change the passphrase")
    option("--forget", action="store_true", help="remove it from your keychain and stop saving it")
    option("--remember", action="store_true", help="save it in your keychain again on the next unlock")

    parser.section("Other")
    option("--version", action="version", version=f"%(prog)s {__version__}", help="show the installed version")
    option("-h", "--help", action="help", help="show this help")
    return parser


def _chosen_actions(args):
    chosen = []
    for name, (flag, _) in ACTIONS.items():
        if flag is None:
            continue
        value = getattr(args, flag[2:].replace("-", "_"))
        if value not in (None, False):
            chosen.append(name)
    return chosen


def parse(argv):
    parser = build_parser()
    # everything after "--" is a search word; intermixed parsing loses track of "--" itself
    literal = []
    if "--" in argv:
        i = argv.index("--")
        argv, literal = argv[:i], argv[i + 1:]
    if any(a == "--editor" or a.startswith("--editor=") for a in argv):
        parser.error("--editor was removed: --edit now asks what to change, no editor needed")
    args = parser.parse_intermixed_args(argv)  # search words may come before and after options
    args.query = args.query + literal
    chosen = _chosen_actions(args)

    if len(chosen) > 1:
        parser.error("use only one of: " + ", ".join(ACTIONS[a][0] for a in chosen))
    action = chosen[0] if chosen else "get"

    if action != "get":
        if args.query and action not in ("export", "edit"):
            parser.error(f"search words can't be combined with {ACTIONS[action][0]}")
        if args.no_copy or args.clear_after is not None:
            parser.error("--no-copy and --clear-after only apply when copying a code")
    if (args.format is not None or args.output is not None) and action != "export":
        parser.error("--format and --output only work with --export")
    if args.output is not None and args.format == "setup-qr":
        parser.error("--output only works with --format uri")

    # names the command handlers expect
    args.action = action
    args.func = ACTIONS[action][1]
    args.names = args.remove_backups or []
    args.name = args.restore
    return args


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        ui.error(msg.ROOT, msg.ROOT_HINT)
        return 1

    args = parse(argv)
    try:
        return args.func(args, make_context())
    except Abort as e:
        ui.error(str(e), *e.hints)
        return 1
    except (KeyboardInterrupt, EOFError):
        print(file=sys.stderr)
        return 130
