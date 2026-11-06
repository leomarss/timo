# Contributing

Thanks for helping with timo. Bug reports, ideas and pull requests are all welcome.

## Setup

```bash
git clone https://github.com/leomarss/timo.git
cd timo
python3 -m venv env
env/bin/pip install --upgrade pip      # editable installs need pip 21.3+
env/bin/pip install -e '.[dev,webcam]'
env/bin/python -m pytest
```

`env/bin/timo` runs your working copy. Set `TIMO_HOME` to a scratch folder so you don't touch your real secrets:

```bash
TIMO_HOME=/tmp/timo-dev env/bin/timo --add
```

## Pull requests

- Keep each pull request to one change, with tests for new behaviour.
- Run `env/bin/python -m pytest` before pushing.
- Write commit messages as [Conventional Commits](https://www.conventionalcommits.org/): `feat: …`, `fix: …`, `docs: …`.
- Add a line under `Unreleased` in [CHANGELOG.md](CHANGELOG.md) for anything a user would notice.
- User-facing text lives in `src/timo/messages.py`, and output formatting in `src/timo/ui.py`.

## Security

Never put real secrets, QR codes or `otpauth://` links in issues, tests or screenshots. To report a vulnerability, see [SECURITY.md](SECURITY.md) instead of opening a public issue.
