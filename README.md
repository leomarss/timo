# TOTP CLI - Terminal One-Time Password

A powerful, terminal-based One-Time Password (TOTP) manager written in Python. Designed for speed, security, and flexibility, with clipboard support, previews, and backup management.

![badge](https://img.shields.io/badge/made%20with-%F0%9F%90%8D%20Python-blue?style=flat-square)

## 🚀 Features

- Interactive TOTP selector using `fzf`
- Search by issuer or account name
- Auto-copy OTP to clipboard
- Preview OTP with color-coded expiration
- Secrets encrypted at rest with your passphrase (scrypt + AES-256-GCM)
- Runs as your normal user, no `sudo`
- Encrypted backups, restore and passphrase change
- Import from Google Authenticator QR (via image)

## 📦 Requirements

- Python 3.9+
- `fzf` installed and available in `$PATH`
- Python packages listed in `src/requirements.txt`
- A virtual environment (recommended)

## 🔧 Setup

```bash
# Clone your repo
cd ~/totp-cli
python3 -m venv env
source env/bin/activate
pip install -r src/requirements.txt
```

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

Create an alias in your shell (bash/zsh):

```bash
alias otpcli='~/totp-cli/env/bin/python ~/totp-cli/src/app.py'
```

Then add your accounts:

```bash
otpcli import
```

The first time, you choose a passphrase. It encrypts your secrets and is asked for on every run. **If you forget it, the secrets cannot be recovered**, so keep your Google Authenticator export (or another copy) somewhere safe.

## ⬆️ Upgrading from the sudo version

Earlier versions ran with `sudo` and kept unencrypted secrets in `json/secrets.json`. To move them:

1. Remove `sudo` from your alias (see above). otpcli now refuses to run as root.
2. Run, as your normal user:
   ```bash
   otpcli migrate
   ```
   It reads the old root-owned file with `sudo cat` (the only step that needs sudo), asks you for a new passphrase, saves the encrypted secrets to `~/.config/totp-cli/`, and offers to delete the old plaintext `json/secrets.json` and `json/backups/`.

## 🧪 Usage

```
otpcli                            Pick an account with fzf and copy its code
otpcli <words...>                 Copy the code if exactly one account matches all words
otpcli get <words...> [--no-copy] Same, explicitly (use it for words like "list")

otpcli list                       Print all account labels
otpcli stats                      Show account counts per issuer
otpcli watch                      Show all codes, refreshing every second
otpcli edit [--backup] [--editor CMD]
                                  Edit the decrypted accounts in your editor
otpcli import                     Import from a Google Authenticator export
otpcli passwd                     Change the passphrase
otpcli migrate [--yes]            Move secrets from the old sudo version

otpcli backup                     Create a backup (same as: backup create)
otpcli backup list                Show available backups
otpcli backup remove <NAMES...>   Delete backups
otpcli backup remove --all        Delete all backups (asks first)
otpcli backup restore <NAME>      Restore a backup (current secrets are backed up first)

otpcli -h | otpcli <command> -h   Help
```

The old flags (`--list`, `--stats`, `--edit`, `--backup`, `--restore`, `--initialize`…) still work and print the new form of the command.

### Importing

`otpcli import` lets you scan a QR code image (e.g. `/home/user/Downloads/otp.png`) with `zbarimg`, or paste the `otpauth-migration://` string (input is hidden). Exports split across several QR codes are imported in full. Importing adds to your existing accounts (after a backup) and skips accounts you already have. Counter-based (HOTP) accounts are not supported and are skipped with a warning.

### Editing

`otpcli edit` decrypts your accounts into a temporary file (inside `~/.config/totp-cli/`, readable only by you), opens your editor, checks the result and re-encrypts it. The temporary file is deleted afterwards. If the edited file isn't valid, you can fix it or discard the changes.

## 🧾 Example Output

```
$ otpcli github
Passphrase:

OTP code for GitHub (you@example.com): 123456
Valid for another 17 seconds (copied to clipboard)
```

```
$ otpcli stats
Passphrase:

TOTP CLI - Account Stats

Total accounts: 6
Unique issuers: 4

  GitHub              -> 2
  Google              -> 2
  AWS                 -> 1
  Bitwarden           -> 1
```

## 🔐 Storage

Everything lives in `~/.config/totp-cli/` (or `$XDG_CONFIG_HOME/totp-cli/`, or the folder in `$TOTP_CLI_HOME`):

```
~/.config/totp-cli/
├── secrets.enc                  # Encrypted accounts
└── backups/
    └── secrets.enc.bak.YYYY-MM-DD_HH-MM-SS
```

`secrets.enc` is encrypted with AES-256-GCM using a key derived from your passphrase with scrypt. The folder is readable only by you (`700`), the files too (`600`).

Decrypted (as shown by `otpcli edit`), the accounts are a JSON list:

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

### Scripting

Set `TOTP_CLI_PASSPHRASE` to skip the prompt, e.g. in a script. Anything running as your user can read a process's environment, so only use it where that's acceptable.

## 🧯 Backup and Restore

- Backups are encrypted copies, kept in `~/.config/totp-cli/backups/`
- `import`, `edit --backup`, `passwd` and `backup restore` back up automatically before changing anything
- Backups keep the passphrase they were made with. Restoring one made before `otpcli passwd` asks for that older passphrase and re-encrypts it with the current one.

```bash
otpcli backup list
otpcli backup restore secrets.enc.bak.2025-04-18_23-30-00
```

## 🧪 Tests

```bash
env/bin/python -m pytest tests
```

## 📁 File Structure

```
totp-cli/
├── env/                         # Python virtual environment
├── src/
│   ├── app.py                   # Main CLI entrypoint
│   ├── monitor.py               # Same as "otpcli watch"
│   ├── requirements.txt
│   └── utils/
│       ├── cli.py               # Argument parsing, old-flag translation
│       ├── commands.py          # Command handlers
│       ├── vault.py             # Encrypted storage
│       ├── utils.py             # OTP generation, backups, helpers
│       ├── preview.py           # Preview shown in fzf
│       └── protobuf/            # Google Authenticator QR importer
│           ├── extract_google_otp_from_qr.py
│           ├── migration_pb2.py
│           └── migration.proto
├── tests/
└── README.md
```

## 📌 Credits

This project uses [`zbarimg`](https://github.com/mchehab/zbar) to scan QR codes from images.  
Make sure it is installed to use `otpcli import` with QR images.


## 💙 License

MIT License. Built for personal security and terminal love. Contributions welcome!
