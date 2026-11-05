# TOTP CLI - Terminal One-Time Password

A powerful, terminal-based One-Time Password (TOTP) manager written in Python. Designed for speed, security, and flexibility, with clipboard support, previews, and backup management.

![badge](https://img.shields.io/badge/made%20with-%F0%9F%90%8D%20Python-blue?style=flat-square)

## 🚀 Features

- Interactive TOTP selector using `fzf`
- Search by issuer or account name
- Auto-copy OTP to clipboard
- Preview OTP with color-coded expiration
- JSON-based secret storage
- Backup and restore support
- Terminal tab renaming
- Import from Google Authenticator QR (via image)

## 📦 Requirements

- Python 3.9+
- `fzf` installed and available in `$PATH`
- Python packages listed in `requirements.txt`
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


## 📁 File Structure

```
totp-cli/
├── env/                         # Python virtual environment
├── json/
│   ├── secrets.json             # Your TOTP secret file
│   └── backups/                 # Backup files
├── src/
│   ├── app.py                   # Main CLI entrypoint
│   ├── monitor.py               # Live TOTP code viewer
│   └── utils/                   # All internal modules
│       ├── preview.py           # Preview shown in fzf
│       ├── utils.py             # General utility functions
│       ├── commands.py          # Command handlers
│       └── protobuf/            # Google Authenticator QR importer
│           ├── extract_google_otp_from_qr.py
│           ├── migration_pb2.py
│           └── migration.proto
├── README.md
└── requirements.txt
```

## 🧪 Usage

```bash
# Run the OTP menu
sudo ./env/bin/python ./src/app.py
```

Or create an alias in your shell (bash/zsh):

```bash
alias otpcli='sudo ~/totp-cli/env/bin/python ~/totp-cli/src/app.py'
```

To import OTP secrets from Google Authenticator, you can use:

```bash
otpcli --initialize
```

If you don't already have the migration string, the script will let you scan a QR code image (e.g. `/home/user/Downloads/otp.png`) using `zbarimg`.  
The OTP secrets will be imported automatically and securely saved.

## 🛠️ Command Line Options

```
otpcli                            Interactive menu with all OTP accounts
otpcli <keyword>                  Filter accounts by keyword(s), auto-copy if exactly one match

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
```

## 🧾 Example Output

```
$ otpcli github

OTP code for GitHub (you@example.com): 123456
Valid for another 17 seconds (copied to clipboard)
```

```
$ otpcli --stats

TOTP CLI - Account Stats

Total accounts: 6
Unique issuers: 4

  GitHub              -> 2
  Google              -> 2
  AWS                 -> 1
  Bitwarden           -> 1
```

## 🔐 OTP Storage Format

All OTP secrets are stored in `json/secrets.json` as a list of dicts:

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

Codes refresh every 30 seconds. Files written before `algorithm` and `digits` were stored keep working with the defaults.

You can import secrets from a Google Authenticator QR code using the `--initialize` command. Importing adds to your existing accounts (after backing up the file) and skips accounts you already have. Counter-based (HOTP) accounts are not supported and are skipped with a warning.

## 🧯 Backup and Restore

- Backups are stored in `json/backups/`
- File format: `secrets.json.bak.YYYY-MM-DD_HH-MM-SS`

To restore:
```bash
otpcli --restore secrets.json.bak.2025-04-18_23-30-00
```

## 📌 Credits

This project uses [`zbarimg`](https://github.com/mchehab/zbar) to scan QR codes from images.  
Make sure it is installed to use `--initialize` with QR import.


## 💙 License

MIT License. Built for personal security and terminal love. Contributions welcome!
