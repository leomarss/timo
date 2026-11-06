# Security policy

timo holds the keys to your two-factor accounts, so security reports are taken seriously.

## Supported versions

Only the latest release gets security fixes.

## Reporting a vulnerability

Please **don't open a public issue**. Report it privately through [GitHub's private vulnerability reporting](https://github.com/leomarss/timo/security/advisories/new) instead.

Include what you found, how to reproduce it, and which version and OS you used. You'll get an answer within a week, and credit in the release notes if you want it.

## How timo protects your secrets

- Secrets are encrypted at rest with AES-256-GCM, using a key derived from your passphrase with scrypt.
- The folder is readable only by you (`700`), the files too (`600`), and writes are crash-safe.
- The passphrase is kept in your OS keychain; `timo --forget` removes it.
- The `fzf` preview gets only upcoming codes, never secrets or the passphrase.
- timo makes no network connections.

Exported `otpauth://` links and files are **not** encrypted: delete them once the other app has imported them.
