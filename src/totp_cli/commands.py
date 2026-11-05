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
    backup_time,
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
from totp_cli import clipboard, fileio, keystore, ui
from totp_cli import messages as msg
from totp_cli.ui import plural
from totp_cli.vault import Vault, VaultFormatError, WrongPassphrase

PASSPHRASE_ENV = "TOTP_CLI_PASSPHRASE"
PREVIEW_ENV = "TOTP_CLI_PREVIEW"
MIN_PASSPHRASE = 8


@dataclass
class Context:
    secrets_path: str
    backup_dir: str
    python_path: str
    preview_script: str
    _vault: Vault = field(default=None, repr=False)


class Abort(Exception):
    """Stop the command with an error (plus optional hint lines) and exit code 1."""

    def __init__(self, message, *hints):
        super().__init__(message)
        self.hints = hints


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
            raise Abort(msg.ENV_PASSPHRASE_TOO_SHORT.format(env=PASSPHRASE_ENV, min=MIN_PASSPHRASE))
        return passphrase
    ui.warn(msg.NEW_PASSPHRASE_INTRO)
    while True:
        first = getpass.getpass(msg.PROMPT_NEW_PASSPHRASE)
        if len(first) < MIN_PASSPHRASE:
            ui.warn(msg.PASSPHRASE_TOO_SHORT.format(min=MIN_PASSPHRASE))
            continue
        if getpass.getpass(msg.PROMPT_REPEAT_PASSPHRASE) != first:
            ui.warn(msg.PASSPHRASES_DIFFER)
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
        ui.note(msg.KEYCHAIN_SAVED)


def open_vault(ctx):
    """Unlock the existing secrets file; returns (vault, accounts)."""
    if ctx._vault is not None:
        return ctx._vault, ctx._vault.load()
    if not os.path.exists(ctx.secrets_path):
        raise Abort(msg.NO_SECRETS.format(path=_rel(ctx.secrets_path)), msg.NO_SECRETS_HINT)

    if _keychain_enabled(ctx):
        saved = keystore.get(ctx.secrets_path)
        if saved is not None:
            vault = Vault(ctx.secrets_path, saved)
            try:
                accounts = vault.load()
            except WrongPassphrase:
                ui.warn(msg.KEYCHAIN_STALE)
            except VaultFormatError as e:
                raise Abort(f"{_rel(ctx.secrets_path)}: {e}")
            else:
                ctx._vault = vault
                return vault, accounts

    attempts = 1 if os.environ.get(PASSPHRASE_ENV) is not None else 3
    for attempt in range(attempts):
        vault = Vault(ctx.secrets_path, _ask(msg.PROMPT_PASSPHRASE))
        try:
            accounts = vault.load()
        except WrongPassphrase as e:
            if attempt + 1 == attempts:
                raise Abort(str(e))
            ui.warn(msg.WRONG_PASSPHRASE_RETRY)
            continue
        except VaultFormatError as e:
            raise Abort(f"{_rel(ctx.secrets_path)}: {e}")
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
        raise Abort(msg.BAD_CLEAR_AFTER_ENV.format(env=clipboard.CLEAR_AFTER_ENV))
    return seconds


def _copy_and_print(acc, args):
    code, remaining = generate_otp(acc)
    if args.no_copy:
        note = msg.NOT_COPIED
    else:
        clear_after = _clear_after(args)
        if not clipboard.copy(code):
            note = msg.CLIPBOARD_UNAVAILABLE
        elif clear_after and clipboard.schedule_clear(code, clear_after):
            note = msg.COPIED_CLEARS.format(seconds=clear_after)
        else:
            note = msg.COPIED
    color = ui.time_color(remaining)
    time_left = ui.paint(msg.TIME_LEFT.format(seconds=remaining), color)
    note = ui.paint("· " + note, ui.DIM)
    if ui.is_terminal():
        shown = ui.paint(ui.group_code(code), ui.BOLD, color)
        ui.box([f"{shown}   {time_left} {note}"], title=ui.paint(label(acc), ui.BOLD))
    else:
        ui.out(label(acc))
        ui.out(f"  {code}   {time_left} {note}")


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
        if not accounts:
            raise Abort(msg.NO_ACCOUNTS, msg.NO_SECRETS_HINT)
        raise Abort(msg.NO_MATCH.format(query=" ".join(args.query)))
    if len(matches) == 1:
        _copy_and_print(matches[0][1], args)
        return 0

    if not _find_fzf():
        raise Abort(msg.NO_FZF, msg.NO_FZF_HINT, msg.NO_FZF_HINT_NARROW,
                    *(f"  {label(acc)}" for _, acc in matches))

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
        ui.note(msg.NOTHING_PICKED)
        return 1

    index_str, _, _ = result.stdout.rstrip("\n").partition("\t")
    try:
        acc = accounts[int(index_str)]
    except (ValueError, IndexError):
        raise Abort(msg.PICKED_UNKNOWN)
    _copy_and_print(acc, args)
    return 0


# --- list / stats / watch ----------------------------------------------------------

def cmd_list(args, ctx):
    _, accounts = open_vault(ctx)
    if not ui.is_terminal():
        for acc in accounts:
            ui.out(label(acc))
        return 0
    ui.table(msg.LIST_HEADERS,
             [(i, acc["issuer"], acc["name"]) for i, acc in enumerate(accounts, 1)], right={0})
    return 0


def cmd_stats(args, ctx):
    _, accounts = open_vault(ctx)
    total, issuer_counts = get_stats(accounts)
    ui.table(msg.STATS_HEADERS, issuer_counts.most_common(), right={1},
             total=(msg.STATS_TOTAL, total),
             note=msg.STATS_ISSUERS.format(issuers=plural(len(issuer_counts), "issuer")))
    return 0


def cmd_watch(args, ctx):
    _, accounts = open_vault(ctx)
    try:
        while True:
            sys.stdout.write("\033[2J\033[H")
            _draw_watch(accounts)
            sys.stdout.flush()
            time.sleep(1)
    except KeyboardInterrupt:
        sys.stdout.write("\033[2J\033[H")
    return 0


def _draw_watch(accounts):
    remaining = 30 - int(time.time()) % 30
    rows = []
    for acc in accounts:
        code, remaining = generate_otp(acc)
        rows.append((code, label(acc)))
    color = ui.time_color(remaining)
    if not ui.is_terminal():
        for code, name in rows:
            ui.out(f"{code}  {name}")
        ui.out(msg.WATCH_PLAIN_FOOTER.format(seconds=remaining))
        return
    lines = [f"{ui.paint(ui.group_code(code), ui.BOLD, color)}   {name}" for code, name in rows]
    footer = [f"{ui.bar(remaining)}  {ui.paint(msg.WATCH_SECONDS.format(seconds=remaining), color)}"
              f"      {ui.paint(msg.WATCH_EXIT, ui.DIM)}"]
    ui.box(lines, title=ui.paint(msg.WATCH_TITLE, ui.BOLD), footer=footer)


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
        raise Abort(msg.NO_EDITOR, msg.NO_EDITOR_HINT)

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
                ui.note(msg.NO_CHANGES)
                return 0
            try:
                edited = json.loads(text)
                validate_accounts(edited)
                break
            except ValueError as e:
                ui.error(msg.INVALID_EDIT.format(error=e))
                if input(msg.PROMPT_EDIT_AGAIN).strip().lower() == "n":
                    ui.warn(msg.CHANGES_DISCARDED)
                    return 1
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    if args.backup:
        ui.ok(msg.BACKUP_SAVED, _rel(create_backup(ctx.secrets_path, ctx.backup_dir)))
    vault.save(edited)
    ui.ok(msg.SAVED_ACCOUNTS.format(accounts=plural(len(edited), "account")))
    return 0


# --- backups -----------------------------------------------------------------------

def cmd_backup_create(args, ctx):
    if not os.path.exists(ctx.secrets_path):
        raise Abort(msg.NOTHING_TO_BACK_UP)
    ui.ok(msg.BACKUP_SAVED, _rel(create_backup(ctx.secrets_path, ctx.backup_dir)))
    return 0


def cmd_backup_list(args, ctx):
    backups = list_backups(ctx.backup_dir)
    if not backups:
        ui.note(msg.NO_BACKUPS)
    elif not ui.is_terminal():
        for b in backups:
            ui.out(b)
    else:
        now = time.time()
        ui.table(msg.BACKUPS_HEADERS,
                 [(b, ui.age(now - backup_time(ctx.backup_dir, b))) for b in backups])
    return 0


def cmd_backup_remove(args, ctx):
    if args.all:
        if args.names:
            raise Abort(msg.NAMES_AND_REMOVE_ALL)
        files = list_backups(ctx.backup_dir)
        if not files:
            ui.note(msg.NO_BACKUPS_TO_REMOVE)
            return 0
        if input(msg.PROMPT_REMOVE_ALL).strip().lower() != "y":
            ui.note(msg.NOTHING_DELETED)
            return 0
        for f in files:
            os.remove(os.path.join(ctx.backup_dir, f))
        ui.ok(msg.REMOVED_ALL.format(backups=plural(len(files), "backup")))
        return 0

    if not args.names:
        raise Abort(msg.REMOVE_NEEDS_NAMES)
    for name in args.names:
        try:
            path = resolve_backup_path(ctx.backup_dir, name)
        except ValueError as e:
            ui.warn(msg.SKIPPED_BACKUP.format(error=e))
            continue
        if os.path.isfile(path):
            os.remove(path)
            ui.ok(msg.REMOVED, name)
        else:
            ui.warn(msg.BACKUP_NOT_FOUND.format(name=name))
    return 0


def cmd_backup_restore(args, ctx):
    try:
        path = resolve_backup_path(ctx.backup_dir, args.name)
    except ValueError as e:
        raise Abort(str(e))
    if not os.path.isfile(path):
        raise Abort(msg.BACKUP_NOT_FOUND.format(name=args.name), msg.BACKUP_NOT_FOUND_HINT)

    if not os.path.exists(ctx.secrets_path):
        with open(path, "rb") as f:
            fileio.write_private(ctx.secrets_path, f.read())
        ui.ok(msg.RESTORED, args.name)
        return 0

    vault, _ = open_vault(ctx)
    try:
        accounts = Vault(path, vault.passphrase).load()
    except WrongPassphrase:
        # made before a passphrase change
        try:
            accounts = Vault(path, _ask(msg.PROMPT_BACKUP_PASSPHRASE)).load()
        except WrongPassphrase as e:
            raise Abort(str(e))
    except VaultFormatError as e:
        raise Abort(msg.BACKUP_UNREADABLE.format(name=args.name, error=e))

    safety = save_with_backup(ctx, vault, accounts)
    ui.ok_rows([(msg.PREVIOUS_BACKED_UP, os.path.basename(safety)), (msg.RESTORED, args.name)])
    return 0


# --- passwd ----------------------------------------------------------------------

def cmd_passwd(args, ctx):
    _, accounts = open_vault(ctx)
    new_vault = Vault(ctx.secrets_path, ask_new_passphrase())
    backup = save_with_backup(ctx, new_vault, accounts)
    ctx._vault = new_vault
    ui.ok(msg.PASSPHRASE_CHANGED)
    _remember(ctx, new_vault.passphrase, announce=False)
    ui.note(msg.BACKUPS_KEEP_OLD_PASSPHRASE.format(backup=_rel(backup)))
    return 0


# --- keychain ----------------------------------------------------------------------

def cmd_forget(args, ctx):
    removed = keystore.delete(ctx.secrets_path)
    os.makedirs(os.path.dirname(ctx.secrets_path), mode=0o700, exist_ok=True)
    with open(_no_keychain_marker(ctx), "w"):
        pass
    if removed:
        ui.ok(msg.KEYCHAIN_REMOVED)
    else:
        ui.note(msg.KEYCHAIN_WAS_EMPTY)
    ui.note(msg.KEYCHAIN_FORGOTTEN_HINT)
    return 0


def cmd_remember(args, ctx):
    marker = _no_keychain_marker(ctx)
    if os.path.exists(marker):
        os.remove(marker)
    if keystore._backend() is None:
        raise Abort(msg.KEYCHAIN_UNAVAILABLE, msg.KEYCHAIN_UNAVAILABLE_HINT)
    ui.ok(msg.KEYCHAIN_WILL_REMEMBER)
    return 0


# --- import ------------------------------------------------------------------------

def _read_migration_uri(use_qr):
    if use_qr:
        return scan_qr_image()
    return read_hidden(msg.PROMPT_PASTE_URI).strip()


def import_into_vault(ctx, new_accounts):
    vault, existing = open_or_create_vault(ctx)
    merged, added = merge_accounts(existing, new_accounts)
    backup = save_with_backup(ctx, vault, merged)
    remember_new_store(ctx)
    if backup:
        ui.ok(msg.PREVIOUS_BACKED_UP, _rel(backup))
    skipped = len(new_accounts) - added
    added_text = plural(added, "new account")
    if skipped:
        ui.ok(msg.IMPORTED_SKIPPED.format(added=added_text, skipped=skipped))
    else:
        ui.ok(msg.IMPORTED.format(added=added_text))
    return added


def _show_qr_batch(accounts, skipped, batch_index, batch_size):
    found = plural(len(accounts), "account")
    if not ui.is_terminal():
        ui.out(msg.FOUND_IN_QR.format(accounts=found, index=batch_index + 1, total=batch_size))
        for acc in accounts:
            ui.out(f"  {label(acc)}")
        for name in skipped:
            ui.warn(msg.SKIPPED_HOTP.format(name=name))
        return
    title = msg.QR_BOX_TITLE.format(index=batch_index + 1, total=batch_size, accounts=found)
    lines = [label(acc) for acc in accounts]
    lines += [f"{ui.paint('!', ui.YELLOW, ui.BOLD)} {msg.SKIPPED_HOTP.format(name=name)}" for name in skipped]
    ui.out()
    ui.box(lines, title=ui.paint(title, ui.BOLD))
    ui.out()


def cmd_import(args, ctx):
    from totp_cli.protobuf.migration import parse_migration_uri

    choice = input(msg.PROMPT_HAVE_URI).strip().lower()
    use_qr = choice != "y"

    collected = []
    while True:
        uri = _read_migration_uri(use_qr)
        if not uri:
            break
        try:
            accounts, skipped, batch_index, batch_size = parse_migration_uri(uri)
        except ValueError as e:
            ui.error(str(e))
            break

        collected.extend(accounts)
        _show_qr_batch(accounts, skipped, batch_index, batch_size)

        if batch_index + 1 >= batch_size:
            break
        more = input(msg.PROMPT_NEXT_QR.format(total=batch_size)).strip().lower()
        if more == "n":
            break

    if not collected:
        raise Abort(msg.NOTHING_IMPORTED)
    import_into_vault(ctx, collected)
    return 0
