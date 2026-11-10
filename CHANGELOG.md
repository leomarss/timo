# Changelog

All notable changes to timo are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Removed

- `src/app.py` and `src/monitor.py`, the old launch scripts. Use the `timo` command (or `python -m timo`, and `timo --watch` for the monitor).

## [3.0.0] - 2026-11-10

### Changed

- `--list` ends with a total: how many accounts and issuers you have.

### Removed

- `--stats`: the total it showed is now at the bottom of `--list`.

## [2.0.1] - 2026-11-06

### Changed

- The README demo shows copying a code with one word, picking one with fzf, and adding an account.
- The README's Python badge reads "3.9+" instead of listing every version.

## [2.0.0] - 2026-11-06

### Changed

- `--edit` is guided: pick an account (`timo --edit github` narrows the list), then it asks for the issuer, name and secret key in turn. Each value comes already typed in, so you fix it with the arrow keys and Enter keeps it, and it's checked as soon as you type it. No editor and no decrypted temp file anymore.
- `--edit` backs up the secrets before saving, like every other change.
- `--remove` goes straight to the confirmation when there is only one account.

### Removed

- `--editor`, and `--backup` as a modifier of `--edit` (`--backup` alone still creates a backup).

## [1.0.3] - 2026-11-06

### Changed

- The README installs webcam support with `pipx install --force 'timo-otp[webcam]'`, which picks the right zxing-cpp for your Python.
- PyPI lists the supported Python versions (3.9 to 3.14).

### Added

- Tests run on every push, on macOS and Linux with Python 3.9 to 3.14.
- `assets/demo/record.sh` records the README demo GIFs again after an output change.

## [1.0.2] - 2026-11-06

### Fixed

- The `webcam` extra now installs on Python 3.9, using zxing-cpp 2.x there (3.x dropped Python 3.9).

## [1.0.1] - 2026-11-06

### Added

- Published on PyPI: `pipx install timo-otp`.
- Demo GIF and banner, each in light and dark mode.
- `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md` and issue templates.

### Changed

- New README with a shorter layout and badges in the banner's colours.
- Package description, keywords and classifiers in `pyproject.toml`.

## [1.0.0] - 2026-11-06

First release as timo (Time-based Identity Manager for OTPs), previously `totp-cli`.

### Added

- Copy a code with one word, or pick an account with `fzf`; the clipboard clears after 45 seconds (`--clear-after`).
- Secrets encrypted at rest with scrypt + AES-256-GCM, passphrase remembered in the OS keychain (`--forget`, `--remember`, `--passwd`).
- `--initialize` imports a Google Authenticator export from a QR image, the webcam or a pasted `otpauth-migration://` link.
- `--add` adds one account from a setup QR code, an `otpauth://` link or a secret key.
- `--export` moves accounts to another app as setup QR codes or `otpauth://` links.
- `--remove` and `--edit` to manage accounts; `--list`, `--stats` and `--watch` to see them.
- Encrypted backups, made automatically before every change (`--backup`, `--restore`, `--list-backups`).
- Webcam QR scanning with a live preview in the terminal (optional `webcam` extra).
- Boxed and table output, coloured by time left, plain output when piped, `NO_COLOR` support.
- Install with `pipx`; runs as your normal user, no `sudo`.

### Fixed

- Per-account algorithm and digits are honoured.
- Imports skip accounts you already have, whatever their label.
- Crash-safe writes for secrets and backups.
- The `fzf` preview works with paths that contain spaces.

[Unreleased]: https://github.com/leomarss/timo/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/leomarss/timo/compare/v2.0.1...v3.0.0
[2.0.1]: https://github.com/leomarss/timo/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/leomarss/timo/compare/v1.0.3...v2.0.0
[1.0.3]: https://github.com/leomarss/timo/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/leomarss/timo/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/leomarss/timo/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/leomarss/timo/releases/tag/v1.0.0
