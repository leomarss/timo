import sys
import os
import shutil
from utils.utils import (
    create_backup,
    restore_backup,
    list_backups,
    get_stats,
    initialize_otp_setup,
    resolve_backup_path
)

HELP_MSG = """
TOTP CLI - Terminal One-Time Password

Usage:
  otpcli                          Interactive menu with all OTP accounts
  otpcli <keyword>                Filter accounts by keyword(s), auto-copy if exactly one match

--help, -h                        Show this help message
--initialize                      Run the setup to import OTP from Google Authenticator
--list                            Print all account labels
--stats                           Show stats per issuer
--edit                            Open the JSON file in default editor
--edit --backup                   Backup file before editing
--edit --editor=<CMD>             Use specific editor (e.g. --editor=vim)
--backup                          Create a manual backup
--backup --remove <FILES...>      Delete one or more backup files
--backup --remove-all             Delete all backup files (with confirmation)
--list-backups                    Show available backup files
--restore <FILENAME>              Restore a specific backup
"""

def handle_commands(argv, accounts, json_path, backup_dir, script_dir):
    known_flags = {
        "--help", "-h", "--initialize", "--list", "--stats",
        "--edit", "--backup", "--remove", "--remove-all",
        "--list-backups", "--restore"
    }

    unrecognized = [arg for arg in argv if arg.startswith("-") and not any(arg.startswith(flag) for flag in known_flags)]
    if unrecognized:
        for cmd in unrecognized:
            print(f"{cmd} command not found. Use --help for usage information.")
        sys.exit(1)
        
    if "--help" in argv or "-h" in argv:
        print(HELP_MSG)
        sys.exit(0)

    if "--list" in argv:
        for acc in accounts:
            print(f"{acc['issuer']} ({acc['name']})")
        sys.exit(0)

    if "--stats" in argv:
        total, issuer_counts = get_stats(accounts)
        print("\nTOTP CLI - Account Stats\n")
        print(f"Total accounts: {total}")
        print(f"Unique issuers: {len(issuer_counts)}\n")
        max_len = max((len(issuer) for issuer in issuer_counts), default=0)
        for issuer, count in issuer_counts.most_common():
            print(f"  {issuer:<{max_len}} -> {count}")
        sys.exit(0)

    if "--edit" in argv:
        editor = next((arg.split("=", 1)[1] for arg in argv if arg.startswith("--editor=")), None)

        if "--backup" in argv:
            path = create_backup(json_path, backup_dir)
            rel_path = os.path.relpath(path, start=os.path.dirname(script_dir))
            print(f"Backup saved to: {rel_path}")

        if not editor:
            editor = os.environ.get("EDITOR")

        if not editor or not shutil.which(editor):
            for fallback in ["vi", "nano", "vim"]:
                if shutil.which(fallback):
                    editor = fallback
                    break
            else:
                print("No suitable editor found.")
                sys.exit(1)

        sys.stdout.flush()  # execvp replaces the process; unflushed output would be lost
        os.execvp(editor, [editor, json_path])
        
    if "--backup" in argv:
        if "--remove" in argv:
            index = argv.index("--remove")
            to_remove = argv[index + 1:]

            if not to_remove:
                print("Please specify at least one backup file to remove.")
                sys.exit(1)

            removed = 0
            for filename in to_remove:
                try:
                    path = resolve_backup_path(backup_dir, filename)
                except ValueError as e:
                    print(f"Skipped: {e}")
                    continue
                if os.path.isfile(path):
                    os.remove(path)
                    print(f"Removed: {filename}")
                    removed += 1
                else:
                    print(f"Not found: {filename}")

            if removed == 0:
                print("No backups removed.")
            sys.exit(0)
        if "--remove-all" in argv:
            files = list_backups(backup_dir)
            if not files:
                print("No backups to remove.")
                sys.exit(0)

            confirm = input("This will delete ALL backups. Are you sure? [y/N] ").strip().lower()
            if confirm != "y":
                print("Aborted.")
                sys.exit(0)

            for f in files:
                os.remove(os.path.join(backup_dir, f))
                print(f"Removed: {f}")

            print("All backups deleted.")
            sys.exit(0)

        path = create_backup(json_path, backup_dir)
        rel_path = os.path.relpath(path, start=os.path.dirname(script_dir))
        print(f"Backup saved to: {rel_path}")
        sys.exit(0)
        
    if "--restore" in argv:
        try:
            index = argv.index("--restore")
            restore_name = argv[index + 1]
        except IndexError:
            print("Please provide the name of the backup file to restore.")
            sys.exit(1)

        try:
            restored = restore_backup(restore_name, backup_dir, json_path)
        except ValueError as e:
            print(e)
            sys.exit(1)
        except FileNotFoundError:
            print(f"Backup not found: {restore_name}. Use --list-backups to see available backups.")
            sys.exit(1)
        print(f"Backup restored from: {restored}")
        sys.exit(0)

    if "--list-backups" in argv:
        print("\nAvailable backups:")
        backups = list_backups(backup_dir)
        if not backups:
            print("  (No backups found)")
        else:
            for b in backups:
                print(f"  {b}")
        sys.exit(0)
        
    if "--initialize" in argv:
        initialize_otp_setup(json_path, backup_dir)
        sys.exit(0)