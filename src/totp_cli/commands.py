"""Command handlers. Each takes (args, ctx) and returns an exit code."""
import getpass
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field

from totp_cli.utils import (
    create_backup,
    fzf_args,
    generate_otp,
    get_stats,
    list_backups,
    merge_accounts,
    preview_codes,
    read_hidden,
    resolve_backup_path,
    scan_qr_image,
    validate_accounts,
)
from totp_cli import clipboard, fileio, keystore
from totp_cli.vault import Vault, VaultFormatError, WrongPassphrase

PASSPHRASE_ENV = "TOTP_CLI_PASSPHRASE"
PREVIEW_ENV = "TOTP_CLI_PREVIEW"
MIN_PASSPHRASE = 8


@dataclass
class Context:
    secrets_path: str
    backup_dir: str
    legacy_json: str  # old sudo version's plaintext file, or None
    python_path: str
    preview_script: str
    _vault: Vault = field(default=None, repr=False)


class Abort(Exception):
    """Stop the command with a message and exit code 1."""


# --- passphrase handling -------------------------------------------------------

def _ask(prompt):
    env = os.environ.get(PASSPHRASE_ENV)
    if env is not None:
        return env
    return getpass.getpass(prompt)


def ask_new_passphrase():
    if os.environ.get(PASSPHRASE_ENV) is not None:
        passphrase = os.environ[PASSPHRASE_ENV]
        if len(passphrase) < MIN_PASSPHRASE:
            raise Abort(f"{PASSPHRASE_ENV} must be at least {MIN_PASSPHRASE} characters.")
        return passphrase
    print("Choose a passphrase to encrypt your secrets. If you forget it, they cannot be recovered.")
    while True:
        first = getpass.getpass("New passphrase: ")
        if len(first) < MIN_PASSPHRASE:
            print(f"Use at least {MIN_PASSPHRASE} characters.")
            continue
        if getpass.getpass("Repeat passphrase: ") != first:
            print("Passphrases did not match, try again.")
            continue
        return first


def _keychain_enabled(ctx):
    # TOTP_CLI_PASSPHRASE means a script or test: leave the keychain alone
    return os.environ.get(PASSPHRASE_ENV) is None and not os.path.exists(_no_keychain_marker(ctx))


def _no_keychain_marker(ctx):
    return os.path.join(os.path.dirname(ctx.secrets_path), "no-keychain")


def _remember(ctx, passphrase, announce=True):
    if not _keychain_enabled(ctx):
        return
    if keystore.get(ctx.secrets_path) == passphrase:
        return
    if keystore.set(ctx.secrets_path, passphrase) and announce:
        print("Passphrase saved in your keychain; otpcli won't ask again on this machine "
              "('otpcli --forget' to undo).")


def open_vault(ctx):
    """Unlock the existing secrets file; returns (vault, accounts)."""
    if ctx._vault is not None:
        return ctx._vault, ctx._vault.load()
    if not os.path.exists(ctx.secrets_path):
        msg = f"No secrets found at {ctx.secrets_path}.\nAdd accounts with:  otpcli --initialize"
        if ctx.legacy_json:
            msg += "\nOr move your secrets from the old sudo version with:  otpcli --migrate"
        raise Abort(msg)

    if _keychain_enabled(ctx):
        saved = keystore.get(ctx.secrets_path)
        if saved is not None:
            vault = Vault(ctx.secrets_path, saved)
            try:
                accounts = vault.load()
            except WrongPassphrase:
                print("The passphrase saved in your keychain no longer works.")
            except VaultFormatError as e:
                raise Abort(f"{ctx.secrets_path}: {e}")
            else:
                ctx._vault = vault
                return vault, accounts

    attempts = 1 if os.environ.get(PASSPHRASE_ENV) is not None else 3
    for attempt in range(attempts):
        vault = Vault(ctx.secrets_path, _ask("Passphrase: "))
        try:
            accounts = vault.load()
        except WrongPassphrase as e:
            if attempt + 1 == attempts:
                raise Abort(str(e))
            print("Wrong passphrase, try again.")
            continue
        except VaultFormatError as e:
            raise Abort(f"{ctx.secrets_path}: {e}")
        ctx._vault = vault
        _remember(ctx, vault.passphrase)
        return vault, accounts


def open_or_create_vault(ctx):
    if os.path.exists(ctx.secrets_path):
        return open_vault(ctx)
    vault = Vault(ctx.secrets_path, ask_new_passphrase())
    ctx._vault = vault
    return vault, []


def remember_new_store(ctx):
    """Call after the first save of a new store, so the keychain entry matches a real file."""
    if ctx._vault is not None:
        _remember(ctx, ctx._vault.passphrase)


def _rel(path):
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home + os.sep) else path


def save_with_backup(ctx, vault, accounts):
    """Back up the current file (if any), then save. Returns the backup path or None."""
    backup = create_backup(ctx.secrets_path, ctx.backup_dir) if os.path.exists(ctx.secrets_path) else None
    vault.save(accounts)
    return backup


# --- get (default) -------------------------------------------------------------

def label(acc):
    return f"{acc['issuer']} ({acc['name']})"


def _clear_after(args):
    if args.clear_after is not None:
        return args.clear_after
    value = os.environ.get(clipboard.CLEAR_AFTER_ENV)
    if value is None:
        return clipboard.DEFAULT_CLEAR_AFTER
    try:
        seconds = int(value)
        if seconds < 0:
            raise ValueError
    except ValueError:
        raise Abort(f"{clipboard.CLEAR_AFTER_ENV} must be a whole number of seconds (0 = never clear).")
    return seconds


def _copy_and_print(acc, args):
    code, remaining = generate_otp(acc)
    if args.no_copy:
        note = "not copied"
    else:
        clear_after = _clear_after(args)
        if not clipboard.copy(code):
            note = "clipboard unavailable"
        elif clear_after and clipboard.schedule_clear(code, clear_after):
            note = f"copied to clipboard, clears in {clear_after}s"
        else:
            note = "copied to clipboard"
    print(f"\nOTP code for {label(acc)}: {code}")
    print(f"Valid for another {remaining} seconds ({note})")


def _find_fzf():
    if shutil.which("fzf"):
        return True
    fallback = os.environ.get("FZF_PATH") or os.path.expanduser("~/.fzf/bin")
    os.environ["PATH"] += os.pathsep + fallback
    return shutil.which("fzf") is not None


def cmd_get(args, ctx):
    _, accounts = open_vault(ctx)
    query = [q.lower() for q in args.query]
    # keep each account's position so duplicate labels stay distinct
    matches = [
        (i, acc) for i, acc in enumerate(accounts)
        if all(q in f"{acc['issuer']} {acc['name']}".lower() for q in query)
    ]
    if not matches:
        print("No matching accounts found.")
        return 1
    if len(matches) == 1:
        _copy_and_print(matches[0][1], args)
        return 0

    if not _find_fzf():
        print("Several accounts match, and fzf (needed to pick one) was not found.")
        print("Install it (brew install fzf / sudo apt install fzf), set FZF_PATH,")
        print("or narrow the search. Matches:")
        for _, acc in matches:
            print(f"  {label(acc)}")
        return 1

    if sys.stdout.isatty():
        sys.stdout.write("\33]0;TOTP CLI - Terminal One-Time Password\a")
        sys.stdout.flush()

    # the preview process gets upcoming codes through its environment, never secrets
    env = dict(os.environ)
    env[PREVIEW_ENV] = json.dumps(preview_codes(matches, time.time()))
    env.pop(PASSPHRASE_ENV, None)
    lines = "\n".join(f"{i}\t{label(acc)}" for i, acc in matches)
    try:
        result = subprocess.run(
            fzf_args(ctx.python_path, ctx.preview_script),
            input=lines, text=True, capture_output=True, check=True, env=env,
        )
    except subprocess.CalledProcessError:
        print("No selection made.")
        return 1

    index_str, _, _ = result.stdout.rstrip("\n").partition("\t")
    try:
        acc = accounts[int(index_str)]
    except (ValueError, IndexError):
        print("Account not found.")
        return 1
    _copy_and_print(acc, args)
    return 0


# --- list / stats / watch ----------------------------------------------------------

def cmd_list(args, ctx):
    _, accounts = open_vault(ctx)
    for acc in accounts:
        print(label(acc))
    return 0


def cmd_stats(args, ctx):
    _, accounts = open_vault(ctx)
    total, issuer_counts = get_stats(accounts)
    print("\nTOTP CLI - Account Stats\n")
    print(f"Total accounts: {total}")
    print(f"Unique issuers: {len(issuer_counts)}\n")
    max_len = max((len(issuer) for issuer in issuer_counts), default=0)
    for issuer, count in issuer_counts.most_common():
        print(f"  {issuer:<{max_len}} -> {count}")
    return 0


def cmd_watch(args, ctx):
    _, accounts = open_vault(ctx)
    try:
        while True:
            sys.stdout.write("\033[2J\033[H")
            print("=== otp list ===\n")
            remaining = 30 - int(time.time()) % 30
            for acc in accounts:
                code, remaining = generate_otp(acc)
                print(f"{code} - {label(acc)}")
            print(f"\nnew codes in {remaining:2d} seconds... (Ctrl-C to exit)")
            sys.stdout.flush()
            time.sleep(1)
    except KeyboardInterrupt:
        sys.stdout.write("\033[2J\033[H")
    return 0


# --- edit --------------------------------------------------------------------------

def _pick_editor(requested):
    for candidate in (requested, os.environ.get("EDITOR"), "vi", "nano", "vim"):
        if candidate and shutil.which(shlex.split(candidate)[0]):
            return shlex.split(candidate)
    return None


def cmd_edit(args, ctx):
    vault, accounts = open_vault(ctx)
    editor = _pick_editor(args.editor)
    if not editor:
        print("No suitable editor found.")
        return 1

    # decrypted copy lives next to the secrets (0700 folder) only while the editor runs
    os.makedirs(os.path.dirname(ctx.secrets_path), mode=0o700, exist_ok=True)
    tmp_path = os.path.join(os.path.dirname(ctx.secrets_path), f".edit-{os.getpid()}.json")
    original = json.dumps(accounts, indent=2) + "\n"
    try:
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(original)
        while True:
            subprocess.run(editor + [tmp_path])
            with open(tmp_path) as f:
                text = f.read()
            if text == original:
                print("No changes.")
                return 0
            try:
                edited = json.loads(text)
                validate_accounts(edited)
                break
            except ValueError as e:
                print(f"Invalid secrets: {e}")
                if input("Edit again? [Y/n] ").strip().lower() == "n":
                    print("Changes discarded.")
                    return 1
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    if args.backup:
        print(f"Backup saved to: {_rel(create_backup(ctx.secrets_path, ctx.backup_dir))}")
    vault.save(edited)
    print(f"Saved {len(edited)} account(s).")
    return 0


# --- backups -----------------------------------------------------------------------

def cmd_backup_create(args, ctx):
    if not os.path.exists(ctx.secrets_path):
        print("Nothing to back up yet.")
        return 1
    print(f"Backup saved to: {_rel(create_backup(ctx.secrets_path, ctx.backup_dir))}")
    return 0


def cmd_backup_list(args, ctx):
    print("\nAvailable backups:")
    backups = list_backups(ctx.backup_dir)
    if not backups:
        print("  (No backups found)")
    for b in backups:
        print(f"  {b}")
    return 0


def cmd_backup_remove(args, ctx):
    if args.all:
        if args.names:
            print("Give backup names or --remove-all, not both.")
            return 1
        files = list_backups(ctx.backup_dir)
        if not files:
            print("No backups to remove.")
            return 0
        if input("This will delete ALL backups. Are you sure? [y/N] ").strip().lower() != "y":
            print("Aborted.")
            return 0
        for f in files:
            os.remove(os.path.join(ctx.backup_dir, f))
            print(f"Removed: {f}")
        print("All backups deleted.")
        return 0

    if not args.names:
        print("Please specify at least one backup file to remove (or --remove-all).")
        return 1
    removed = 0
    for name in args.names:
        try:
            path = resolve_backup_path(ctx.backup_dir, name)
        except ValueError as e:
            print(f"Skipped: {e}")
            continue
        if os.path.isfile(path):
            os.remove(path)
            print(f"Removed: {name}")
            removed += 1
        else:
            print(f"Not found: {name}")
    if removed == 0:
        print("No backups removed.")
    return 0


def cmd_backup_restore(args, ctx):
    try:
        path = resolve_backup_path(ctx.backup_dir, args.name)
    except ValueError as e:
        print(e)
        return 1
    if not os.path.isfile(path):
        print(f"Backup not found: {args.name}. Use 'otpcli --list-backups' to see available backups.")
        return 1

    if not os.path.exists(ctx.secrets_path):
        with open(path, "rb") as f:
            fileio.write_private(ctx.secrets_path, f.read())
        print(f"Backup restored from: {args.name}")
        return 0

    vault, _ = open_vault(ctx)
    try:
        accounts = Vault(path, vault.passphrase).load()
    except WrongPassphrase:
        # made before a passphrase change
        try:
            accounts = Vault(path, _ask("This backup uses an older passphrase. Passphrase for the backup: ")).load()
        except WrongPassphrase as e:
            print(e)
            return 1
    except VaultFormatError as e:
        print(f"{args.name}: {e}")
        return 1

    safety = save_with_backup(ctx, vault, accounts)
    print(f"Previous secrets saved to: {_rel(safety)}")
    print(f"Backup restored from: {args.name}")
    return 0


# --- passwd ----------------------------------------------------------------------

def cmd_passwd(args, ctx):
    _, accounts = open_vault(ctx)
    new_vault = Vault(ctx.secrets_path, ask_new_passphrase())
    backup = save_with_backup(ctx, new_vault, accounts)
    ctx._vault = new_vault
    print("Passphrase changed.")
    _remember(ctx, new_vault.passphrase, announce=False)
    print(f"Backups (including {_rel(backup)}) keep the passphrase they were made with.")
    return 0


# --- keychain ----------------------------------------------------------------------

def cmd_forget(args, ctx):
    removed = keystore.delete(ctx.secrets_path)
    os.makedirs(os.path.dirname(ctx.secrets_path), mode=0o700, exist_ok=True)
    with open(_no_keychain_marker(ctx), "w"):
        pass
    print("Passphrase removed from your keychain." if removed else "No passphrase was saved in your keychain.")
    print("otpcli will ask for it every time. Use 'otpcli --remember' to save it again.")
    return 0


def cmd_remember(args, ctx):
    marker = _no_keychain_marker(ctx)
    if os.path.exists(marker):
        os.remove(marker)
    if keystore._backend() is None:
        print("No usable keychain on this machine, so otpcli will keep asking for the passphrase.")
        return 1
    print("otpcli will save your passphrase in the keychain the next time you unlock.")
    return 0


# --- import ------------------------------------------------------------------------

def _read_migration_uri(use_qr):
    if use_qr:
        return scan_qr_image()
    return read_hidden("Paste otpauth-migration string (input hidden): ").strip()


def import_into_vault(ctx, new_accounts):
    vault, existing = open_or_create_vault(ctx)
    merged, added = merge_accounts(existing, new_accounts)
    backup = save_with_backup(ctx, vault, merged)
    remember_new_store(ctx)
    if backup:
        print(f"\nPrevious secrets backed up to: {_rel(backup)}")
    skipped = len(new_accounts) - added
    print(f"Imported {added} new account(s)" + (f", skipped {skipped} already present." if skipped else "."))
    return added


def cmd_import(args, ctx):
    from totp_cli.protobuf.migration import parse_migration_uri

    choice = input("Do you already have the OTP migration string? [y/N] ").strip().lower()
    use_qr = choice != "y"

    collected = []
    while True:
        uri = _read_migration_uri(use_qr)
        if not uri:
            break
        try:
            accounts, skipped, batch_index, batch_size = parse_migration_uri(uri)
        except ValueError as e:
            print(f"Error: {e}")
            break

        collected.extend(accounts)
        print(f"\nFound {len(accounts)} account(s) (QR {batch_index + 1} of {batch_size}):")
        for acc in accounts:
            print(f"  {label(acc)}")
        for name in skipped:
            print(f"  Skipped {name}: counter-based (HOTP) accounts are not supported.")

        if batch_index + 1 >= batch_size:
            break
        more = input(f"\nThe export has {batch_size} QR codes. Import the next one? [Y/n] ").strip().lower()
        if more == "n":
            break

    if not collected:
        print("Nothing imported.")
        return 1
    import_into_vault(ctx, collected)
    return 0


# --- migrate (from the old sudo version) -------------------------------------------

def _read_legacy(path):
    try:
        with open(path) as f:
            return f.read()
    except PermissionError:
        print(f"{path} is owned by root; reading it with sudo (you may be asked for your password).")
        result = subprocess.run(["sudo", "cat", path], capture_output=True, text=True)
        if result.returncode != 0:
            raise Abort(f"Could not read {path}: {result.stderr.strip()}")
        return result.stdout


def _remove_legacy(paths):
    existing = [p for p in paths if os.path.exists(p)]
    try:
        for p in existing:
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
    except PermissionError:
        result = subprocess.run(["sudo", "rm", "-rf", "--"] + existing)
        if result.returncode != 0:
            print("Could not delete the old files; remove them manually:")
            for p in existing:
                print(f"  sudo rm -rf {shlex.quote(p)}")
            return
    for p in existing:
        print(f"Deleted: {p}")


def cmd_migrate(args, ctx):
    path = args.migrate_path or ctx.legacy_json
    if not path or not os.path.exists(path):
        from totp_cli.cli import legacy_candidates
        looked = [path] if args.migrate_path else legacy_candidates()
        print("No old secrets file found. Looked in:")
        for p in looked:
            print(f"  {p}")
        print("If it's somewhere else, run:  otpcli --migrate PATH")
        return 1
    try:
        accounts = json.loads(_read_legacy(path))
        validate_accounts(accounts)
    except ValueError as e:
        print(f"{path} is not a valid secrets file: {e}")
        return 1

    print(f"Found {len(accounts)} account(s) in {path}.")
    import_into_vault(ctx, accounts)
    print(f"Secrets are now encrypted at {_rel(ctx.secrets_path)}.")

    old_backups = os.path.join(os.path.dirname(path), "backups")
    targets = [path] + ([old_backups] if os.path.isdir(old_backups) else [])
    print("\nThe old files are still unencrypted:")
    for t in targets:
        print(f"  {t}")
    if args.yes or input("Delete them now? [y/N] ").strip().lower() == "y":
        _remove_legacy(targets)
    else:
        print("Kept. Delete them once you've checked everything works.")
    return 0
