"""Every message otpcli shows, in one place.

How a message looks (symbol, colour, stdout or stderr) is decided by the
ui function that prints it, not here. Conventions:
- start with a capital letter, no full stop at the end
- no "please"; say what happened, then what to do (as a hint line)
- {placeholders} are filled in with str.format()
"""

# --- yes/no questions (ui.confirm adds [y/N] or [Y/n]) -----------------------------
PRESS_Y_OR_N = "(press y or n)"
ANSWER_YES = "yes"
ANSWER_NO = "no"

# --- general -----------------------------------------------------------------------
ROOT = "otpcli doesn't run as root"
ROOT_HINT = "Run it as your normal user, without sudo"
NO_SECRETS = "No secrets found at {path}"
NO_SECRETS_HINT = "Add accounts with: otpcli --initialize (or otpcli --add for one)"

# --- passphrase --------------------------------------------------------------------
PROMPT_PASSPHRASE = "Passphrase: "
PROMPT_NEW_PASSPHRASE = "New passphrase: "
PROMPT_REPEAT_PASSPHRASE = "Repeat passphrase: "
PROMPT_BACKUP_PASSPHRASE = "This backup uses an older passphrase. Passphrase for the backup: "
NEW_PASSPHRASE_INTRO = "Choose a passphrase to encrypt your secrets. If you forget it, they can't be recovered"
PASSPHRASE_TOO_SHORT = "Use at least {min} characters"
ENV_PASSPHRASE_TOO_SHORT = "{env} must be at least {min} characters"
PASSPHRASES_DIFFER = "Passphrases didn't match, try again"
WRONG_PASSPHRASE_RETRY = "Wrong passphrase, try again"
PASSPHRASE_CHANGED = "Passphrase changed"
BACKUPS_KEEP_OLD_PASSPHRASE = "Backups (including {backup}) keep the passphrase they were made with"

# --- keychain ----------------------------------------------------------------------
KEYCHAIN_SAVED = "Passphrase saved in your keychain; otpcli won't ask again on this machine (otpcli --forget to undo)"
KEYCHAIN_STALE = "The passphrase saved in your keychain no longer works"
KEYCHAIN_REMOVED = "Passphrase removed from your keychain"
KEYCHAIN_WAS_EMPTY = "No passphrase was saved in your keychain"
KEYCHAIN_FORGOTTEN_HINT = "otpcli will ask for it every time. Use otpcli --remember to save it again"
KEYCHAIN_UNAVAILABLE = "No usable keychain on this machine"
KEYCHAIN_UNAVAILABLE_HINT = "otpcli will keep asking for the passphrase"
KEYCHAIN_WILL_REMEMBER = "otpcli will save your passphrase in the keychain the next time you unlock"

# --- getting a code ----------------------------------------------------------------
NO_ACCOUNTS = "No accounts yet"
NO_MATCH = "No account matches \"{query}\""
NO_FZF = "Several accounts match"
NO_FZF_HINT = "fzf (needed to pick one) isn't installed: brew install fzf / sudo apt install fzf"
NO_FZF_HINT_NARROW = "Or narrow the search:"
NOTHING_PICKED = "No account picked"
PICKED_UNKNOWN = "Account not found"
TIME_LEFT = "{seconds}s left"
NOT_COPIED = "not copied"
CLIPBOARD_UNAVAILABLE = "clipboard unavailable"
COPIED = "copied"
COPIED_CLEARS = "copied, clears in {seconds}s"
BAD_CLEAR_AFTER_ENV = "{env} must be a whole number of seconds (0 = never clear)"

# --- list / stats / watch ----------------------------------------------------------
LIST_HEADERS = ("#", "Issuer", "Account", "Added")
NO_DATE = "-"
STATS_HEADERS = ("Issuer", "Accounts")
STATS_TOTAL = "Total"
STATS_ISSUERS = "({issuers})"
WATCH_TITLE = "otpcli --watch"
WATCH_SECONDS = "{seconds:2d}s"
WATCH_EXIT = "Ctrl-C to exit"
WATCH_PLAIN_FOOTER = "New codes in {seconds:2d}s · Ctrl-C to exit"

# --- edit --------------------------------------------------------------------------
NO_EDITOR = "No suitable editor found"
NO_EDITOR_HINT = "Set $EDITOR or use --editor=<command>"
NO_CHANGES = "No changes"
INVALID_EDIT = "Invalid accounts: {error}"
PROMPT_EDIT_AGAIN = "Edit again?"
CHANGES_DISCARDED = "Changes discarded"
SAVED_ACCOUNTS = "Saved {accounts}"

# --- backups -----------------------------------------------------------------------
NOTHING_TO_BACK_UP = "Nothing to back up yet"
BACKUP_SAVED = "Backup saved"
PREVIOUS_BACKED_UP = "Previous secrets backed up"
NO_BACKUPS = "No backups yet"
BACKUPS_HEADERS = ("Backup", "Age")
AGE_JUST_NOW = "just now"
AGE_UNITS = ((60, "minute"), (3600, "hour"), (86400, "day"), (7 * 86400, "week"),
             (30 * 86400, "month"), (365 * 86400, "year"))
NO_BACKUPS_TO_REMOVE = "No backups to remove"
PROMPT_REMOVE_ALL = "This will delete ALL backups. Are you sure?"
NOTHING_DELETED = "Nothing deleted"
REMOVED_ALL = "Removed {backups}"
REMOVED = "Removed"
SKIPPED_BACKUP = "Skipped {error}"
BACKUP_NOT_FOUND = "Backup not found: {name}"
BACKUP_NOT_FOUND_HINT = "See the available backups with: otpcli --list-backups"
RESTORED = "Restored"
BACKUP_UNREADABLE = "{name}: {error}"

# --- import ------------------------------------------------------------------------
PROMPT_HAVE_URI = "Do you already have the OTP migration string?"
PROMPT_PASTE_URI = "Paste otpauth-migration string (input hidden): "
PROMPT_QR_PATH = "Path to QR code image (e.g. ~/Downloads/otp.png), or Enter to use the webcam: "
PROMPT_NEXT_QR = "The export has {total} QR codes. Import the next one?"
FOUND_IN_QR = "Found {accounts} in QR {index} of {total}:"
QR_BOX_TITLE = "QR {index} of {total} · {accounts}"
SKIPPED_HOTP = "Skipped {name}: counter-based (HOTP) accounts aren't supported"
NOTHING_IMPORTED = "Nothing imported"
IMPORTED = "Imported {added}"
IMPORTED_SKIPPED = "Imported {added}, skipped {skipped} already present"
QR_NOT_FOUND = "File not found: {path}"
QR_NOT_A_FILE = "Not a file: {path}"
QR_NOT_READABLE = "Can't read {path}: check its permissions"
NO_ZBARIMG = "zbarimg isn't installed"
NO_ZBARIMG_HINT = "Install it with: brew install zbar / sudo apt install zbar-tools"
SCANNING_QR = "Scanning QR code…"
QR_UNREADABLE = "zbarimg couldn't read a QR code in {path}"
SCANNING_WEBCAM = "Opening the webcam…"
WEBCAM_PREVIEW_STATUS = "Show the QR code to the camera · Esc or q to cancel"
NO_WEBCAM_EXTRA = "Scanning with the webcam needs PyAV and zxing-cpp"
NO_WEBCAM_EXTRA_HINT = "Install them with: pipx inject totp-cli av zxing-cpp"
WEBCAM_UNSUPPORTED = "Scanning with the webcam works on macOS and Linux only"
WEBCAM_NO_TERMINAL = "Scanning with the webcam needs a terminal to show the camera in"
WEBCAM_UNAVAILABLE = "Can't use the webcam"
WEBCAM_UNAVAILABLE_HINT_MACOS = ("Allow your terminal app in System Settings › Privacy & Security › Camera, "
                                 "then try again")
WEBCAM_UNAVAILABLE_HINT_LINUX = "Check that a camera is connected at /dev/video0 and that you can read it (the video group)"

# --- add ---------------------------------------------------------------------------
PROMPT_HAVE_KEY = "Do you already have the otpauth:// link or the secret key?"
PROMPT_PASTE_KEY = "Paste the otpauth:// link or the secret key (input hidden): "
PROMPT_ISSUER = "Issuer (e.g. GitHub): "
PROMPT_ACCOUNT_NAME = "Account name (e.g. you@example.com): "
PROMPT_REPLACE = "{name} already exists with a different secret key. Replace it?"
IS_MIGRATION = "That's a Google Authenticator export, not a single account"
IS_MIGRATION_HINT = "Import it with: otpcli --initialize"
ALREADY_PRESENT = "{name} is already present"
NOTHING_ADDED = "Nothing added"
ADDED = "Added {name}"
REPLACED = "Replaced {name}"

# --- export ------------------------------------------------------------------------
PROMPT_SHOW_SECRETS = "Show the secret keys of {accounts} on screen, unencrypted?"
NOTHING_EXPORTED = "Nothing exported"
EXPORT_NEEDS_TERMINAL = "Setup QR codes need a terminal to show them in"
EXPORT_NEEDS_TERMINAL_HINT = "Export otpauth:// links instead with: otpcli --export --format uri"
EXPORT_NO_FOLDER = "Folder not found: {path}"
EXPORT_EXISTS = "{path} already exists"
EXPORT_EXISTS_HINT = "Choose another file name: otpcli never overwrites one"
EXPORT_WRITE_FAILED = "Can't write {path}: {error}"
EXPORTED_TO = "Exported {accounts} to"
EXPORT_NOT_ENCRYPTED = "The file isn't encrypted: delete it once you've imported the accounts"
QR_EXPORT_TITLE = "{name} · {index} of {total}"
QR_EXPORT_HINT = "Scan it with your authenticator app"
PROMPT_NEXT_ACCOUNT = "Show the next account?"
PROMPT_DONE_SCANNING = "Press Enter when you're done "
EXPORTED_QR = "Showed {accounts} as QR codes"
EXPORTED_SOME_QR = "Showed {shown} of {total} accounts as QR codes"

# --- remove ------------------------------------------------------------------------
FZF_REMOVE_PROMPT = "Remove account: "
PROMPT_REMOVE_NUMBER = "Number of the account to remove (Enter to cancel): "
BAD_NUMBER = "Type a number from 1 to {count}"
PROMPT_REMOVE_ACCOUNT = "Remove {name}?"
NOTHING_REMOVED = "Nothing removed"
REMOVED_ACCOUNT = "Removed {name}"
