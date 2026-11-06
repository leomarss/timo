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

## Demo GIFs

The README GIFs are recorded with [vhs](https://github.com/charmbracelet/vhs) on a throwaway vault with fake accounts. After a change to timo's output, record both again:

```bash
brew install vhs
assets/demo/record.sh
```

## Releasing

1. Move the `Unreleased` entries in [CHANGELOG.md](CHANGELOG.md) into a `## [X.Y.Z] - YYYY-MM-DD` section, and set `__version__` in `src/timo/__init__.py` to `X.Y.Z`.
2. Commit, push, then tag and push the tag:

   ```bash
   git tag -a vX.Y.Z -m "timo X.Y.Z" && git push origin vX.Y.Z
   ```

The tag starts the release workflow: it checks the tag against `__version__` and the changelog, uploads to PyPI, then creates the GitHub release with that version's changelog section as notes. Preview the notes with `.github/scripts/release-notes.sh X.Y.Z`. Push the tag only: creating the release on GitHub by hand makes the workflow fail at its last step.
