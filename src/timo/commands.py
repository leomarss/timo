"""Command handlers. Each takes (args, ctx) and returns an exit code."""
import getpass
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from dataclasses import dataclass, field

from timo.utils import (
    backup_time,
    create_backup,
    fzf_args,
    generate_otp,
    list_backups,
    make_totp,
    merge_accounts,
    now_stamp,
    preview_codes,
    read_hidden,
    resolve_backup_path,
    scan_qr_image,
    secret_key,
)
from timo import clipboard, fileio, keystore, ui
from timo import messages as msg
from timo.ui import plural
from timo.vault import Vault, VaultFormatError, WrongPassphrase

PASSPHRASE_ENV = "TIMO_PASSPHRASE"
PREVIEW_ENV = "TIMO_PREVIEW"
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
    # TIMO_PASSPHRASE means a script or test: leave the keychain alone
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


def _matching(accounts, words):
    """[(index, account)] for the accounts whose label contains every word.

    Keeps each account's position so duplicate labels stay distinct. Aborts
    when nothing matches.
    """
    query = [q.lower() for q in words]
    matches = [
        (i, acc) for i, acc in enumerate(accounts)
        if all(q in f"{acc['issuer']} {acc['name']}".lower() for q in query)
    ]
    if not matches:
        if not accounts:
            raise Abort(msg.NO_ACCOUNTS, msg.NO_SECRETS_HINT)
        raise Abort(msg.NO_MATCH.format(query=" ".join(words)))
    return matches


def cmd_get(args, ctx):
    _, accounts = open_vault(ctx)
    matches = _matching(accounts, args.query)
    if len(matches) == 1:
        _copy_and_print(matches[0][1], args)
        return 0

    if not _find_fzf():
        raise Abort(msg.NO_FZF, msg.NO_FZF_HINT, msg.NO_FZF_HINT_NARROW,
                    *(f"  {label(acc)}" for _, acc in matches))

    index = _pick_with_fzf(ctx, accounts, matches)
    if index is None:
        ui.note(msg.NOTHING_PICKED)
        return 1
    _copy_and_print(accounts[index], args)
    return 0


def _pick_with_fzf(ctx, accounts, matches, prompt="Select OTP: ", show_date=False):
    """Let the user pick one of matches [(index, account)] with fzf.

    show_date adds the day each account was added after its label, lined up.
    Returns the picked account's index in accounts, or None if they pressed Esc.
    """
    if sys.stdout.isatty():
        sys.stdout.write("\33]0;timo - Time-based Identity Manager for OTPs\a")
        sys.stdout.flush()

    # the preview process gets upcoming codes through its environment, never secrets
    env = dict(os.environ)
    env[PREVIEW_ENV] = json.dumps(preview_codes(matches, time.time()))
    env.pop(PASSPHRASE_ENV, None)
    shown = [label(acc) for _, acc in matches]
    if show_date:
        width = max(map(len, shown))
        shown = [f"{text.ljust(width)}   {_date_added(acc)}" for text, (_, acc) in zip(shown, matches)]
    lines = "\n".join(f"{i}\t{text}" for (i, _), text in zip(matches, shown))
    try:
        result = subprocess.run(
            fzf_args(ctx.python_path, ctx.preview_script, prompt),
            input=lines, text=True, capture_output=True, check=True, env=env,
        )
    except subprocess.CalledProcessError:
        return None

    index_str, _, _ = result.stdout.rstrip("\n").partition("\t")
    try:
        index = int(index_str)
        accounts[index]
    except (ValueError, IndexError):
        raise Abort(msg.PICKED_UNKNOWN)
    return index


# --- list / watch ----------------------------------------------------------

def cmd_list(args, ctx):
    _, accounts = open_vault(ctx)
    if not ui.is_terminal():
        for acc in accounts:
            ui.out(label(acc))
        return 0
    issuers = len({acc["issuer"] for acc in accounts})
    _account_table(accounts, total=("", msg.LIST_TOTAL, plural(len(accounts), "account"), ""),
                   note=msg.LIST_ISSUERS.format(issuers=plural(issuers, "issuer")))
    return 0


def _account_table(accounts, total=None, note=""):
    ui.table(msg.LIST_HEADERS,
             [(i, acc["issuer"], acc["name"], _date_added(acc)) for i, acc in enumerate(accounts, 1)],
             right={0}, total=total, note=note)


def _date_added(acc):
    """The day an account was added ("2026-11-05"), or "-" for accounts from before date_added."""
    value = acc.get("date_added")
    if not value:
        return msg.NO_DATE
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d")
    except ValueError:
        return value  # edited by hand: show it as it is


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

def cmd_edit(args, ctx):
    vault, accounts = open_vault(ctx)
    index = _pick_account(ctx, accounts, _matching(accounts, args.query),
                          msg.FZF_EDIT_PROMPT, msg.PROMPT_EDIT_NUMBER)
    if index is None:
        ui.note(msg.NOTHING_CHANGED)
        return 0

    old = accounts[index]
    others = accounts[:index] + accounts[index + 1:]
    ui.out(ui.paint(msg.EDITING.format(name=label(old)), ui.BOLD))
    ui.note(msg.EDIT_HINT)
    acc = dict(old)
    for step in (_edit_text("issuer", msg.FIELD_ISSUER), _edit_text("name", msg.FIELD_NAME), _edit_secret):
        acc = _until_valid(step, acc, others)

    changes = _edit_changes(old, acc)
    if not changes:
        ui.note(msg.NO_CHANGES)
        return 0
    if ui.is_terminal():
        ui.out()
    for line in changes:
        ui.out(f"{ui.paint(msg.CHANGE_BULLET, ui.CYAN)} {line}")
    if ui.is_terminal():
        ui.out()
    if not ui.confirm(msg.PROMPT_SAVE_EDIT, default=True):
        ui.warn(msg.CHANGES_DISCARDED)
        return 0

    backup = save_with_backup(ctx, vault, accounts[:index] + [acc] + accounts[index + 1:])
    ui.ok(msg.PREVIOUS_BACKED_UP, _rel(backup))
    ui.ok(msg.SAVED_ACCOUNT.format(name=label(acc)))
    return 0


def _until_valid(step, acc, others):
    """Run one question of --edit, asking again until the answer is usable."""
    while True:
        try:
            return step(acc, others)
        except ValueError as e:
            ui.error(str(e))


def _edit_text(field, title):
    def edit(acc, others):
        changed = {**acc, field: ui.ask(title, acc[field])}
        if changed[field] == acc[field]:
            return acc  # kept: even a label two accounts already share stays as it is
        taken = next((o for o in others if _same_account(o, changed)), None)
        if taken is not None:
            raise ValueError(msg.LABEL_TAKEN.format(name=label(taken)))
        return changed
    return edit


def _edit_secret(acc, others):
    from timo.otpauth import normalize_secret

    text = read_hidden(msg.PROMPT_NEW_SECRET).strip()
    if not text:
        return acc
    changed = {**acc, "secret": normalize_secret(text)}
    make_totp(changed).now()
    taken = next((o for o in others if secret_key(o["secret"]) == changed["secret"]), None)
    if taken is not None:
        raise ValueError(msg.SECRET_TAKEN.format(name=label(taken)))
    return changed


def _edit_changes(old, new):
    """One line per changed field, e.g. "Name: me → work"; never shows a secret.

    On a terminal the old value is dimmed and the new value is bold.
    """
    def dim(text):
        return ui.paint(text, ui.DIM)

    def bold(text):
        return ui.paint(text, ui.BOLD)

    pairs = ((msg.FIELD_ISSUER, old["issuer"], new["issuer"]), (msg.FIELD_NAME, old["name"], new["name"]))
    lines = [msg.CHANGED_FROM_TO.format(field=f"{f}:", old=dim(a), new=bold(b)) for f, a, b in pairs if a != b]
    if secret_key(old["secret"]) != secret_key(new["secret"]):
        lines.append(msg.CHANGED_TO.format(field=f"{msg.FIELD_SECRET}:", new=bold(msg.SECRET_CHANGED)))
    return lines


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


def cmd_backup_remove_all(args, ctx):
    files = list_backups(ctx.backup_dir)
    if not files:
        ui.note(msg.NO_BACKUPS_TO_REMOVE)
        return 0
    if not ui.confirm(msg.PROMPT_REMOVE_ALL):
        ui.note(msg.NOTHING_DELETED)
        return 0
    for f in files:
        os.remove(os.path.join(ctx.backup_dir, f))
    ui.ok(msg.REMOVED_ALL.format(backups=plural(len(files), "backup")))
    return 0


def cmd_backup_remove(args, ctx):
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

def _read_migration_uri(use_qr, seen=()):
    if use_qr:
        return scan_qr_image(seen)
    return read_hidden(msg.PROMPT_PASTE_URI).strip()


def import_into_vault(ctx, new_accounts):
    vault, existing = open_or_create_vault(ctx)
    stamp = now_stamp()
    merged, added = merge_accounts(existing, [{**acc, "date_added": stamp} for acc in new_accounts])
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
    from timo.protobuf.migration import parse_migration_uri

    use_qr = not ui.confirm(msg.PROMPT_HAVE_URI)

    collected = []
    seen = set()
    while True:
        uri = _read_migration_uri(use_qr, seen)
        if not uri:
            break
        seen.add(uri)
        try:
            accounts, skipped, batch_index, batch_size = parse_migration_uri(uri)
        except ValueError as e:
            ui.error(str(e))
            break

        collected.extend(accounts)
        _show_qr_batch(accounts, skipped, batch_index, batch_size)

        if batch_index + 1 >= batch_size:
            break
        if not ui.confirm(msg.PROMPT_NEXT_QR.format(total=batch_size), default=True):
            break

    if not collected:
        raise Abort(msg.NOTHING_IMPORTED)
    import_into_vault(ctx, collected)
    return 0


# --- add ---------------------------------------------------------------------------

def _read_single_account():
    """Ask for one account (pasted link or key, or a QR code); returns an account dict."""
    from timo.otpauth import normalize_secret, parse_otpauth_uri

    pasted = ui.confirm(msg.PROMPT_HAVE_KEY)
    text = (read_hidden(msg.PROMPT_PASTE_KEY) if pasted else scan_qr_image() or "").strip()
    if not text:
        raise Abort(msg.NOTHING_ADDED)
    if text.lower().startswith("otpauth-migration:"):
        raise Abort(msg.IS_MIGRATION, msg.IS_MIGRATION_HINT)

    try:
        if text.lower().startswith("otpauth:"):
            acc = parse_otpauth_uri(text)
        else:
            acc = {"issuer": "", "name": "", "secret": normalize_secret(text),
                   "algorithm": "SHA1", "digits": 6}
        make_totp(acc).now()  # unsupported algorithm or digits
    except ValueError as e:
        raise Abort(str(e))

    for field, prompt in (("issuer", msg.PROMPT_ISSUER), ("name", msg.PROMPT_ACCOUNT_NAME)):
        while not acc[field]:
            acc[field] = input(prompt).strip()
    return acc


def _same_account(a, b):
    return (a["issuer"].casefold(), a["name"].casefold()) == (b["issuer"].casefold(), b["name"].casefold())


def cmd_add(args, ctx):
    acc = _read_single_account()
    vault, accounts = open_or_create_vault(ctx)
    acc["date_added"] = now_stamp()

    same_key = next((old for old in accounts if secret_key(old["secret"]) == secret_key(acc["secret"])), None)
    if same_key is not None:  # whatever its label
        ui.warn(msg.ALREADY_PRESENT.format(name=label(same_key)))
        return 0

    match = next((i for i, old in enumerate(accounts) if _same_account(old, acc)), None)
    if match is None:
        accounts = accounts + [acc]
        done = msg.ADDED.format(name=label(acc))
    else:
        old = accounts[match]
        if not ui.confirm(msg.PROMPT_REPLACE.format(name=label(old))):
            raise Abort(msg.NOTHING_ADDED)
        # keep the label you had (maybe renamed with --edit), take the new key
        acc = {**acc, "issuer": old["issuer"], "name": old["name"]}
        accounts = accounts[:match] + [acc] + accounts[match + 1:]
        done = msg.REPLACED.format(name=label(acc))

    backup = save_with_backup(ctx, vault, accounts)
    remember_new_store(ctx)
    if ui.is_terminal():
        ui.out()
    _copy_and_print(acc, args)  # sites ask for a code to finish turning on 2FA
    if ui.is_terminal():
        ui.out()
    if backup:
        ui.ok(msg.PREVIOUS_BACKED_UP, _rel(backup))
    ui.ok(done)
    return 0


# --- export ------------------------------------------------------------------------

ALT_SCREEN_ON = "\033[?1049h"  # QR codes go on the alternate screen, so they don't stay
ALT_SCREEN_OFF = "\033[?1049l"  # in the scrollback once timo is done
CLEAR_SCREEN = "\033[2J\033[H"


def cmd_export(args, ctx):
    from timo.otpauth import to_otpauth_uri

    _, accounts = open_vault(ctx)
    chosen = [acc for _, acc in _matching(accounts, args.query)]
    found = plural(len(chosen), "account")
    fmt = args.format or ("uri" if args.output or not ui.is_terminal() else "setup-qr")

    if fmt == "setup-qr":
        if not ui.is_terminal():
            raise Abort(msg.EXPORT_NEEDS_TERMINAL, msg.EXPORT_NEEDS_TERMINAL_HINT)
        return _show_setup_qrs(chosen)

    links = "".join(to_otpauth_uri(acc) + "\n" for acc in chosen)
    if args.output:
        _write_export(os.path.expanduser(args.output), links)
        ui.ok(msg.EXPORTED_TO.format(accounts=found), args.output)
        ui.warn(msg.EXPORT_NOT_ENCRYPTED)
        return 0
    if ui.is_terminal() and not ui.confirm(msg.PROMPT_SHOW_SECRETS.format(accounts=found)):
        ui.note(msg.NOTHING_EXPORTED)
        return 0
    sys.stdout.write(links)
    return 0


def _write_export(path, text):
    folder = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(folder):  # don't create folders on the way
        raise Abort(msg.EXPORT_NO_FOLDER.format(path=folder))
    try:
        fileio.write_new_private(path, text.encode())
    except FileExistsError:
        raise Abort(msg.EXPORT_EXISTS.format(path=path), msg.EXPORT_EXISTS_HINT)
    except OSError as e:
        raise Abort(msg.EXPORT_WRITE_FAILED.format(path=path, error=e.strerror or e))


def _show_setup_qrs(accounts):
    from timo import qr
    from timo.otpauth import to_otpauth_uri

    total = len(accounts)
    shown = 0
    sys.stdout.write(ALT_SCREEN_ON)
    try:
        for index, acc in enumerate(accounts, 1):
            sys.stdout.write(CLEAR_SCREEN)
            title = msg.QR_EXPORT_TITLE.format(name=label(acc), index=index, total=total)
            ui.out(ui.paint(title, ui.BOLD))
            ui.out()
            ui.out("\n".join(qr.terminal_lines(to_otpauth_uri(acc))))
            ui.out()
            ui.out(ui.paint(msg.QR_EXPORT_HINT, ui.DIM))
            shown += 1
            if index == total:
                input(msg.PROMPT_DONE_SCANNING)
            elif not ui.confirm(msg.PROMPT_NEXT_ACCOUNT, default=True):
                break
    finally:
        sys.stdout.write(ALT_SCREEN_OFF)
        sys.stdout.flush()
    if shown == total:
        ui.ok(msg.EXPORTED_QR.format(accounts=plural(total, "account")))
    else:
        ui.ok(msg.EXPORTED_SOME_QR.format(shown=shown, total=total))
    return 0


# --- remove ------------------------------------------------------------------------

def _pick_account(ctx, accounts, matches, fzf_prompt, number_prompt):
    """The index of the account to act on, among matches [(index, account)].

    The only match is taken as it is; otherwise the user picks one with fzf,
    or from a numbered list without it. None if they cancelled.
    """
    if len(matches) == 1:
        return matches[0][0]
    if _find_fzf():
        return _pick_with_fzf(ctx, accounts, matches, prompt=fzf_prompt, show_date=True)
    return _pick_by_number(matches, number_prompt)


def _pick_by_number(matches, prompt):
    """Show matches [(index, account)] numbered from 1 and ask for a number; None for Enter."""
    shown = [acc for _, acc in matches]
    if ui.is_terminal():
        _account_table(shown)
    else:
        width = len(str(len(shown)))
        for i, acc in enumerate(shown, 1):
            ui.out(f"{i:>{width}}  {label(acc)}")
    while True:
        answer = input(prompt).strip()
        if not answer:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(shown):
            return matches[int(answer) - 1][0]
        ui.warn(msg.BAD_NUMBER.format(count=len(shown)))


def cmd_remove(args, ctx):
    vault, accounts = open_vault(ctx)
    if not accounts:
        raise Abort(msg.NO_ACCOUNTS, msg.NO_SECRETS_HINT)

    index = _pick_account(ctx, accounts, list(enumerate(accounts)), msg.FZF_REMOVE_PROMPT,
                          msg.PROMPT_REMOVE_NUMBER)
    if index is None or not ui.confirm(msg.PROMPT_REMOVE_ACCOUNT.format(name=label(accounts[index]))):
        ui.note(msg.NOTHING_REMOVED)
        return 0

    removed = accounts[index]
    backup = save_with_backup(ctx, vault, accounts[:index] + accounts[index + 1:])
    ui.ok(msg.PREVIOUS_BACKED_UP, _rel(backup))
    ui.ok(msg.REMOVED_ACCOUNT.format(name=label(removed)))
    return 0
