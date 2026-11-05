# TOTP CLI - Terminal One-Time Password

A powerful, terminal-based One-Time Password (TOTP) manager written in Python. Designed for speed, security, and flexibility, with clipboard support, previews, and backup management.

![badge](https://img.shields.io/badge/made%20with-%F0%9F%90%8D%20Python-blue?style=flat-square)

## 🚀 Features

- Interactive TOTP selector using `fzf`
- Search by issuer or account name
- Auto-copy OTP to clipboard, cleared again after 45 seconds
- Preview OTP with color-coded expiration
- Secrets encrypted at rest with your passphrase (scrypt + AES-256-GCM)
- Passphrase remembered in your OS keychain, so you type it once per machine
- Runs as your normal user, no `sudo`
- Encrypted backups, restore and passphrase change
- Import from Google Authenticator QR (via image)
- Add single accounts from a site's 2FA setup QR code, `otpauth://` link or secret key

## 📦 Requirements

- Python 3.9+
- [`pipx`](https://pipx.pypa.io/) (`brew install pipx` or `sudo apt install pipx`)
- `fzf` installed and available in `$PATH`
- `zbarimg` to import from QR code images (optional)

## 🔧 Setup

```bash
pipx install git+https://github.com/leomarss/totp-cli.git
# or, from a local clone:
pipx install ~/totp-cli
```

This puts an `otpcli` command on your `PATH`, in its own isolated environment. To update later: `pipx upgrade totp-cli` (or `pipx install --force ~/totp-cli` for a local clone).

Make sure `fzf` is installed:
```bash
sudo apt install fzf   # Debian/Ubuntu
# or
brew install fzf       # macOS
```

To import OTP secrets from a Google QR code:
```bash
sudo apt install zbar-tools   # Debian/Ubuntu
# or
brew install zbar       # macOS
```

If `fzf` is installed but not found by the script, you can set its path manually:

```bash
export FZF_PATH=$(dirname $(which fzf))
```

Then add your accounts:

```bash
otpcli --initialize
```

The first time, you choose a passphrase. It encrypts your secrets. **If you forget it, the secrets cannot be recovered**, so keep your Google Authenticator export (or another copy) somewhere safe.

After the first unlock, otpcli saves the passphrase in your OS keychain and stops asking (see [Keychain](#-keychain)).

## 🧪 Usage

```
otpcli                            Pick an account with fzf and copy its code
otpcli <words...>                 Copy the code if exactly one account matches all words
    --no-copy                     Print the code without copying it
    --clear-after SECONDS         Clear the clipboard after SECONDS (0 = never; default 45)
otpcli -- <words...>              Search for words that start with "-"

--list                            Print all account labels
--stats                           Show account counts per issuer
--watch                           Show all codes, refreshing every second
--edit                            Edit the decrypted accounts in your editor
--edit --backup                   Back up before saving the changes
--edit --editor=<CMD>             Use a specific editor (e.g. --editor=vim)
--initialize                      Import from a Google Authenticator export
--add                             Add one account (setup QR code, otpauth:// link or secret key)
--passwd                          Change the passphrase
--forget                          Remove the passphrase from the keychain and stop saving it
--remember                        Save it in the keychain again on the next unlock

--backup                          Create a backup
--list-backups                    Show available backups
--backup --remove <NAMES...>      Delete backups
--backup --remove-all             Delete all backups (asks first)
--restore <NAME>                  Restore a backup (current secrets are backed up first)

--version                         Show the installed version
--help, -h                        Help
```

Every option starts with `-` or `--`, and plain words are always a search, so an account can be called "edit" or "list". Options must be spelled out in full, and only one action can be used at a time.

### Importing

`otpcli --initialize` lets you scan a QR code image (e.g. `/home/user/Downloads/otp.png`) with `zbarimg`, or paste the `otpauth-migration://` string (input is hidden). Exports split across several QR codes are imported in full. Importing adds to your existing accounts (after a backup) and skips accounts you already have. Counter-based (HOTP) accounts are not supported and are skipped with a warning.

### Adding an account

`otpcli --add` adds a single account when you turn on two-factor authentication on a site, so you don't need Google Authenticator at all. Scan the setup QR code from an image (e.g. a screenshot of the setup page), or paste the `otpauth://` link or the secret key the site shows under "can't scan the code?" (input is hidden; spaces and dashes are fine). For a bare key, otpcli asks for the issuer and account name.

The current code is shown and copied right away, since most sites ask for one to finish the setup. If the account already exists with a different key (you reset 2FA on that site), otpcli asks before replacing it and keeps your label. Only 30-second codes are supported, and a Google Authenticator export belongs in `--initialize`.

### Editing

`otpcli --edit` decrypts your accounts into a temporary file (inside `~/.config/totp-cli/`, readable only by you), opens your editor, checks the result and re-encrypts it. The temporary file is deleted afterwards. If the edited file isn't valid, you can fix it or discard the changes.

## 🧾 Example Output

```
$ otpcli github
╭─ GitHub (you@example.com) ────────────────────╮
│  482 913   17s left · copied, clears in 45s   │
╰───────────────────────────────────────────────╯
```

The code is shown as `482 913` to make it easier to read; the clipboard gets `482913`.

```
$ otpcli --stats
 Issuer     Accounts
 ─────────  ────────
 GitHub            2
 Google            2
 AWS               1
 Bitwarden         1
 ─────────  ────────
 Total             6   (4 issuers)

$ otpcli --list-backups
 Backup                               Age
 ───────────────────────────────────  ───────
 secrets.enc.bak.2026-10-12_18-30-00  3 weeks
 secrets.enc.bak.2026-11-01_09-02-41  4 days

$ otpcli --backup
✓ Backup saved  ~/.config/totp-cli/backups/secrets.enc.bak.2026-11-05_11-20-03

$ otpcli gihub
✗ No account matches "gihub"
```

In a terminal the code is coloured by the time it has left (green, then yellow, then red). Errors (`✗`) and warnings (`!`) go to stderr. When the output isn't a terminal (a pipe or a script), boxes and tables are left out: you get the bare code (`482913`) and one name per line from `--list` and `--list-backups`. Colour turns off there too, and whenever [`NO_COLOR`](https://no-color.org) is set.

## 🔐 Storage

Everything lives in `~/.config/totp-cli/` (or `$XDG_CONFIG_HOME/totp-cli/`, or the folder in `$TOTP_CLI_HOME`):

```
~/.config/totp-cli/
├── secrets.enc                  # Encrypted accounts
└── backups/
    └── secrets.enc.bak.YYYY-MM-DD_HH-MM-SS
```

`secrets.enc` is encrypted with AES-256-GCM using a key derived from your passphrase with scrypt. The folder is readable only by you (`700`), the files too (`600`). Every save and backup is written to a temporary file, flushed to disk, and only then renamed into place, so a crash or full disk never leaves a half-written file.

Decrypted (as shown by `otpcli --edit`), the accounts are a JSON list:

```json
[
  {
    "issuer": "GitHub",
    "name": "you@example.com",
    "secret": "JBSWY3DPEHPK3PXP",
    "algorithm": "SHA1",
    "digits": 6
  }
]
```

| Field | Required | Values | Default |
|---|---|---|---|
| `issuer` | yes | any string | |
| `name` | yes | any string | |
| `secret` | yes | base32 secret | |
| `algorithm` | no | `SHA1`, `SHA256`, `SHA512`, `MD5` | `SHA1` |
| `digits` | no | `6`, `8` | `6` |

Codes refresh every 30 seconds.

### The fzf preview

The preview runs as a separate process, so it can't ask for your passphrase. otpcli hands it only the upcoming codes (10 minutes' worth) through an environment variable, which only your user can read. It never gets your secrets or passphrase. If the picker stays open longer, the preview asks you to reopen otpcli.

### Clipboard

After copying a code, otpcli clears the clipboard 45 seconds later, but only if it still holds that code, so anything you copied since is left alone. otpcli doesn't wait for this: a small background process does it. Change the delay with `--clear-after SECONDS` or `export TOTP_CLI_CLEAR_AFTER=SECONDS`; `0` turns clearing off.

### Scripting

Set `TOTP_CLI_PASSPHRASE` to skip the prompt, e.g. in a script. Anything running as your user can read a process's environment, so only use it where that's acceptable. When it is set, otpcli doesn't read or write the keychain.

## 🔑 Keychain

The first time you unlock, otpcli saves the passphrase in your OS keychain (entry `totp-cli`) and doesn't ask again on that machine:

- **macOS:** Keychain. macOS may ask once to allow Python access.
- **Linux desktop:** GNOME Keyring / KWallet (Secret Service), normally unlocked when you log in.
- **No keychain** (SSH sessions, headless servers, WSL, containers): otpcli asks for the passphrase each time, as before.

otpcli never uses "keyrings" that store passwords in a plain file. If the saved passphrase stops working (e.g. after `otpcli --passwd` elsewhere), otpcli asks again and updates it. `otpcli --passwd` updates it too.

Anyone using your unlocked session can get codes without the passphrase. To go back to typing it every time, run `otpcli --forget`; `otpcli --remember` turns it back on.

## 🧯 Backup and Restore

- Backups are encrypted copies, kept in `~/.config/totp-cli/backups/`
- `import`, `edit --backup`, `passwd` and `backup restore` back up automatically before changing anything
- Backups keep the passphrase they were made with. Restoring one made before `otpcli --passwd` asks for that older passphrase and re-encrypts it with the current one.

```bash
otpcli --list-backups
otpcli --restore secrets.enc.bak.2025-04-18_23-30-00
```

## 🛠️ Development

```bash
cd ~/totp-cli
python3 -m venv env
env/bin/pip install --upgrade pip   # editable installs need pip 21.3+
env/bin/pip install -e '.[dev]'
env/bin/python -m pytest
```

`env/bin/otpcli` then runs your working copy. `python src/app.py` works too.

## 📁 File Structure

```
totp-cli/
├── pyproject.toml               # Package metadata and dependencies
├── src/
│   ├── app.py                   # Run from a checkout without installing
│   ├── monitor.py               # Same as "otpcli --watch"
│   └── totp_cli/
│       ├── cli.py               # Argument parsing, "otpcli" entry point
│       ├── commands.py          # Command handlers
│       ├── vault.py             # Encrypted storage
│       ├── keystore.py          # OS keychain for the passphrase
│       ├── fileio.py            # Crash-safe private file writes
│       ├── clipboard.py         # Copy and delayed clear
│       ├── messages.py          # The text of every message
│       ├── ui.py                # How output is shown (boxes, tables, colour, stdout/stderr)
│       ├── utils.py             # OTP generation, backups, helpers
│       ├── preview.py           # Preview shown in fzf
│       └── protobuf/            # Google Authenticator export decoding
│           ├── migration.py
│           ├── migration_pb2.py
│           └── migration.proto
├── tests/
└── README.md
```

## 📌 Credits

This project uses [`zbarimg`](https://github.com/mchehab/zbar) to scan QR codes from images.  
Make sure it is installed to use `otpcli --initialize` or `otpcli --add` with QR images.


## 💙 License

MIT License. Built for personal security and terminal love. Contributions welcome!
