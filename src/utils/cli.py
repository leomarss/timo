"""Command-line entry point: argparse subcommands plus translation of the old flags."""
import argparse
import os
import sys

from utils import commands
from utils.commands import Abort, Context

SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(SRC_DIR)

SUBCOMMANDS = {"get", "list", "stats", "watch", "edit", "backup", "import", "passwd", "migrate", "help"}

DESCRIPTION = "TOTP CLI - Terminal One-Time Password"
EPILOG = """\
examples:
  otpcli                     pick an account with fzf and copy its code
  otpcli github              copy the code if exactly one account matches "github"
  otpcli backup restore <NAME>
  otpcli <command> -h        help for one command

Secrets are encrypted with your passphrase in ~/.config/totp-cli/
(override with TOTP_CLI_HOME).
"""


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


def build_parser():
    parser = argparse.ArgumentParser(
        prog="otpcli", description=DESCRIPTION, epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p = sub.add_parser("get", help="copy a code (default when you just type search words)")
    p.add_argument("query", nargs="*", help="words that must all appear in issuer or account name")
    p.add_argument("--no-copy", action="store_true", help="print the code without copying it")
    p.set_defaults(func=commands.cmd_get)

    sub.add_parser("list", help="print all account labels").set_defaults(func=commands.cmd_list)
    sub.add_parser("stats", help="show account counts per issuer").set_defaults(func=commands.cmd_stats)
    sub.add_parser("watch", help="show all codes, refreshing every second").set_defaults(func=commands.cmd_watch)

    p = sub.add_parser("edit", help="edit the decrypted accounts in your editor")
    p.add_argument("--backup", action="store_true", help="back up before saving changes")
    p.add_argument("--editor", metavar="CMD", help="editor to use (default: $EDITOR, then vi/nano/vim)")
    p.set_defaults(func=commands.cmd_edit)

    backup = sub.add_parser("backup", help="create, list, remove or restore backups")
    bsub = backup.add_subparsers(dest="backup_command", metavar="<action>")
    bsub.add_parser("create", help="create a backup now").set_defaults(func=commands.cmd_backup_create)
    bsub.add_parser("list", help="list backups").set_defaults(func=commands.cmd_backup_list)
    p = bsub.add_parser("remove", help="delete backups")
    p.add_argument("names", nargs="*", metavar="NAME")
    p.add_argument("--all", action="store_true", help="delete every backup (asks first)")
    p.set_defaults(func=commands.cmd_backup_remove)
    p = bsub.add_parser("restore", help="restore a backup (the current secrets are backed up first)")
    p.add_argument("name", metavar="NAME")
    p.set_defaults(func=commands.cmd_backup_restore)
    backup.set_defaults(func=commands.cmd_backup_create)  # plain "otpcli backup"

    sub.add_parser("import", help="import accounts from a Google Authenticator export").set_defaults(func=commands.cmd_import)
    sub.add_parser("passwd", help="change the passphrase").set_defaults(func=commands.cmd_passwd)

    p = sub.add_parser("migrate", help="move secrets from the old sudo version (json/secrets.json)")
    p.add_argument("--yes", action="store_true", help="delete the old plaintext files without asking")
    p.set_defaults(func=commands.cmd_migrate)

    sub.add_parser("help", help="show this help")
    return parser


LEGACY_FLAGS = {
    "--initialize", "--list", "--stats", "--edit", "--backup", "--remove",
    "--remove-all", "--list-backups", "--restore",
}

LEGACY_HINTS = {
    "--initialize": "import",
    "--list": "list",
    "--stats": "stats",
    "--list-backups": "backup list",
}


def translate_legacy(argv):
    """Map the old flag interface onto subcommands. Returns (argv, hint or None)."""
    if not argv or argv[0] in SUBCOMMANDS:
        return argv, None
    if not any(a in LEGACY_FLAGS or a.startswith("--editor=") for a in argv):
        return argv, None

    def after(flag):
        return argv[argv.index(flag) + 1:]

    if "--edit" in argv:
        new = ["edit"]
        if "--backup" in argv:
            new.append("--backup")
        for a in argv:
            if a.startswith("--editor="):
                new += ["--editor", a.split("=", 1)[1]]
    elif "--backup" in argv and "--remove-all" in argv:
        new = ["backup", "remove", "--all"]
    elif "--backup" in argv and "--remove" in argv:
        new = ["backup", "remove"] + after("--remove")
    elif "--backup" in argv:
        new = ["backup", "create"]
    elif "--restore" in argv:
        new = ["backup", "restore"] + after("--restore")[:1]
    else:
        flag = next((a for a in argv if a in LEGACY_HINTS), None)
        if flag is None:
            return argv, None
        new = LEGACY_HINTS[flag].split()

    old = " ".join(a for a in argv if a.startswith("-"))
    return new, f"Note: '{old}' is now 'otpcli {' '.join(new)}'. The old flags still work for now."



def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("otpcli no longer runs as root. Run it as your normal user (remove sudo from your alias).")
        print("Moving from the old sudo version? Run as yourself:  otpcli migrate")
        return 1

    argv, hint = translate_legacy(argv)
    if hint:
        print(hint, file=sys.stderr)

    # anything that isn't a command name (search words, --no-copy, nothing) means "get"
    if not argv or (argv[0] not in SUBCOMMANDS and argv[0] not in ("-h", "--help")):
        argv = ["get"] + argv

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "help":
        parser.print_help()
        return 0

    try:
        return args.func(args, make_context())
    except Abort as e:
        print(e)
        return 1
    except (KeyboardInterrupt, EOFError):
        print()
        return 130
