# Changelog

All notable changes to timo are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- New README with the timo banner, a shorter layout and badges in the banner's colours.
- Package description, keywords and classifiers in `pyproject.toml`.

### Added

- `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md` and issue templates.

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

[Unreleased]: https://github.com/leomarss/timo/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/leomarss/timo/releases/tag/v1.0.0
