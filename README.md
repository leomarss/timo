<h1 align="center">
  <img src="assets/banner.png" width="100%" alt="timo: encrypted at rest, no phone needed, no network. Fast, encrypted, import from Google Authenticator or any QR, export to any other app">
</h1>

<p align="center">
  <b>Your authenticator app, in the terminal, one word away.</b><br>
  <sub><i>Time-based Identity Manager for OTPs</i></sub>
</p>

<p align="center">
  <img alt="Python 3.9+" src="https://img.shields.io/badge/python-3.9%2B-3776ab?style=flat-square&logo=python&logoColor=white">
  <img alt="macOS · Linux" src="https://img.shields.io/badge/macOS%20%C2%B7%20Linux-supported-444?style=flat-square">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-444?style=flat-square">
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#usage">Usage</a> ·
  <a href="#security">Security</a> ·
  <a href="#development">Development</a>
</p>

<br>

```
$ timo github
╭─ GitHub (you@example.com) ────────────────────╮
│  482 913   17s left · copied, clears in 45s   │
╰───────────────────────────────────────────────╯
```

<br>

Type a word, get the code on your clipboard. No phone, no app switching. Pick from a fuzzy list with `fzf` when you're not sure, import everything from Google Authenticator in one go, and take it all with you when you leave.

<br>

## Install

```bash
brew install pipx fzf               # Debian/Ubuntu: sudo apt install pipx fzf
pipx install git+https://github.com/leomarss/timo.git

# Optional: scan QR codes from images and with the webcam
brew install zbar                   # Debian/Ubuntu: sudo apt install zbar-tools
pipx inject timo-otp av zxing-cpp
```

Update with `pipx upgrade timo-otp`.

<br>

## Usage

```bash
timo --initialize    # import a Google Authenticator export (first run sets your passphrase)
timo --add           # add one account from a setup QR, otpauth:// link or secret key
timo github          # copy the code of the account matching "github"
timo                 # pick an account with fzf
```

| Command | What it does |
|---|---|
| `timo WORDS` | Copy the code of the matching account (`--no-copy` to just print it) |
| `--list` · `--stats` | List accounts, or count them per issuer |
| `--watch` | Show every code, live |
| `--add` · `--remove` · `--edit` | Manage single accounts |
| `--export [WORDS]` | Move accounts to another app (`--format uri` for links) |
| `--backup` · `--restore NAME` | Encrypted backups, made automatically before every change |
| `--passwd` · `--forget` | Change the passphrase, or drop it from the keychain |

Run `timo --help` for the full list. Plain words are always a search, so an account can be called `edit` or `list`.

> [!WARNING]
> Your passphrase encrypts everything. **If you forget it, the secrets cannot be recovered**, so keep your original export somewhere safe.

<br>

## Security

- 🗝️ Secrets live in `~/.config/timo/secrets.enc` (override with `TIMO_HOME`), with `700`/`600` permissions and crash-safe writes.
- The `fzf` preview never sees your secrets or passphrase, only the next 10 minutes of codes.
- `--edit` temp files are deleted, webcam frames stay in memory, and export QR codes are cleared from scrollback.
- Exported `otpauth://` links are **not** encrypted: delete them once imported.
- No `sudo`, no network.

<br>

## Development

```bash
python3 -m venv env
env/bin/pip install -e '.[dev]'
env/bin/python -m pytest
```

<br>

## License

MIT. Built on [fzf](https://github.com/junegunn/fzf), [zbar](https://github.com/mchehab/zbar), [PyAV](https://github.com/PyAV-Org/PyAV) and [zxing-cpp](https://github.com/zxing-cpp/zxing-cpp).
