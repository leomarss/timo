"""Command-line entry point.

Every option starts with '-' or '--'; plain words are always a search, so an
account can be called "edit" or "list" without clashing with a command.
"""
import argparse
import os
import sys

from utils import commands
from utils.commands import Abort, Context

SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(SRC_DIR)

DESCRIPTION = "TOTP CLI - Terminal One-Time Password"
EPILOG = """\
examples:
  otpcli                     pick an account with fzf and copy its code
  otpcli github              copy the code if exactly one account matches "github"
  otpcli --edit --backup     back up, then edit the accounts
  otpcli -- -weird           search for a word that starts with "-"

Secrets are encrypted with your passphrase in ~/.config/totp-cli/
(override with TOTP_CLI_HOME).
"""

# action name -> (flag, handler)
ACTIONS = {
    "list": ("--list", commands.cmd_list),
    "stats": ("--stats", commands.cmd_stats),
    "watch": ("--watch", commands.cmd_watch),
    "edit": ("--edit", commands.cmd_edit),
    "initialize": ("--initialize", commands.cmd_import),
    "passwd": ("--passwd", commands.cmd_passwd),
    "forget": ("--forget", commands.cmd_forget),
    "remember": ("--remember", commands.cmd_remember),
    "migrate": ("--migrate", commands.cmd_migrate),
    "list-backups": ("--list-backups", commands.cmd_backup_list),
    "restore": ("--restore", commands.cmd_backup_restore),
    "remove": ("--remove", commands.cmd_backup_remove),
    "remove-all": ("--remove-all", commands.cmd_backup_remove),
    "backup": ("--backup", commands.cmd_backup_create),
    "get": (None, commands.cmd_get),
}


def config_dir():
    if os.environ.get("TOTP_CLI_HOME"):
        return os.environ["TOTP_CLI_HOME"]
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "totp-cli")


def make_context():
    home = config_dir()
    return Context(
        secrets_path=os.path.join(home, "secrets.enc"),
        backup_dir=os.path.join(home, "backups"),
        legacy_json=os.path.join(REPO_DIR, "json", "secrets.json"),
        python_path=sys.executable,
        preview_script=os.path.join(SRC_DIR, "utils", "preview.py"),
    )


def _seconds(value):
    try:
        seconds = int(value)
    except ValueError:
        seconds = -1
    if seconds < 0:
        raise argparse.ArgumentTypeError("must be a whole number of seconds (0 = never clear)")
    return seconds


def build_parser():
    parser = argparse.ArgumentParser(
        prog="otpcli",
        usage="otpcli [WORDS...] [--no-copy] [--clear-after SECONDS]\n       otpcli --<action> [options]",
        description=DESCRIPTION, epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,  # flags must be spelled out: --lis is not --list
    )
    parser.add_argument("query", nargs="*", metavar="WORDS",
                        help="copy the code of the account matching all words (fzf picker if several match)")

    get = parser.add_argument_group("copying a code")
    get.add_argument("--no-copy", action="store_true", help="print the code without copying it")
    get.add_argument("--clear-after", type=_seconds, metavar="SECONDS",
                     help="clear the clipboard after SECONDS, 0 = never (default: $TOTP_CLI_CLEAR_AFTER or 45)")

    acts = parser.add_argument_group("actions")
    acts.add_argument("--list", action="store_true", help="print all account labels")
    acts.add_argument("--stats", action="store_true", help="show account counts per issuer")
    acts.add_argument("--watch", action="store_true", help="show all codes, refreshing every second")
    acts.add_argument("--edit", action="store_true", help="edit the decrypted accounts in your editor")
    acts.add_argument("--editor", metavar="CMD", help="with --edit: editor to use (default: $EDITOR, then vi/nano/vim)")
    acts.add_argument("--initialize", action="store_true", help="import accounts from a Google Authenticator export")
    acts.add_argument("--passwd", action="store_true", help="change the passphrase")
    acts.add_argument("--forget", action="store_true", help="remove the passphrase from your keychain and stop saving it")
    acts.add_argument("--remember", action="store_true", help="save the passphrase in your keychain again")
    acts.add_argument("--migrate", action="store_true", help="move secrets from the old sudo version (json/secrets.json)")
    acts.add_argument("--yes", action="store_true", help="with --migrate: delete the old plaintext files without asking")

    backups = parser.add_argument_group("backups")
    backups.add_argument("--backup", action="store_true",
                         help="create a backup (with --edit: back up before saving changes)")
    backups.add_argument("--list-backups", action="store_true", help="show available backups")
    backups.add_argument("--restore", metavar="NAME", help="restore a backup (current secrets are backed up first)")
    backups.add_argument("--remove", nargs="+", metavar="NAME", help="delete backups (also: --backup --remove NAME...)")
    backups.add_argument("--remove-all", action="store_true", help="delete all backups (asks first)")
    return parser


def _chosen_actions(args):
    chosen = []
    for name, (flag, _) in ACTIONS.items():
        if flag is None:
            continue
        value = getattr(args, flag[2:].replace("-", "_"))
        if value not in (None, False):
            chosen.append(name)
    # --backup is a modifier of --edit, --remove and --remove-all
    if "backup" in chosen and any(a in chosen for a in ("edit", "remove", "remove-all")):
        chosen.remove("backup")
    return chosen


def parse(argv):
    parser = build_parser()
    # everything after "--" is a search word; intermixed parsing loses track of "--" itself
    literal = []
    if "--" in argv:
        i = argv.index("--")
        argv, literal = argv[:i], argv[i + 1:]
    args = parser.parse_intermixed_args(argv)  # search words may come before and after options
    args.query = args.query + literal
    chosen = _chosen_actions(args)

    if len(chosen) > 1:
        parser.error("use only one of: " + ", ".join(ACTIONS[a][0] for a in chosen))
    action = chosen[0] if chosen else "get"

    if action != "get":
        if args.query:
            parser.error(f"search words can't be combined with {ACTIONS[action][0]}")
        if args.no_copy or args.clear_after is not None:
            parser.error("--no-copy and --clear-after only apply when copying a code")
    if args.editor is not None and action != "edit":
        parser.error("--editor only works with --edit")
    if args.yes and action != "migrate":
        parser.error("--yes only works with --migrate")

    # names the command handlers expect
    args.action = action
    args.func = ACTIONS[action][1]
    args.names = args.remove or []
    args.all = args.remove_all
    args.name = args.restore
    return args


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("otpcli no longer runs as root. Run it as your normal user (remove sudo from your alias).")
        print("Moving from the old sudo version? Run as yourself:  otpcli --migrate")
        return 1

    args = parse(argv)
    try:
        return args.func(args, make_context())
    except Abort as e:
        print(e)
        return 1
    except (KeyboardInterrupt, EOFError):
        print()
        return 130
