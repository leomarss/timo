import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))
sys.path.insert(0, os.path.abspath(os.path.join(SRC, "utils", "protobuf")))

PASSPHRASE = "test passphrase"


@pytest.fixture
def cli(tmp_path, monkeypatch, capsys):
    """Run otpcli's main() against a temporary config folder.

    Returns an object with run(*argv, answers=[...]) -> (exit_code, stdout, stderr),
    plus the paths it uses. Prompts answered by input() come from `answers`.
    """
    from utils import cli as cli_module
    from utils import vault

    from utils import keystore

    monkeypatch.setattr(vault, "SCRYPT_N", 2**10)  # fast tests
    monkeypatch.setattr(keystore, "_backend", lambda: None)  # never touch the real keychain
    home = tmp_path / "config"
    monkeypatch.setenv("TOTP_CLI_HOME", str(home))
    monkeypatch.setenv("TOTP_CLI_PASSPHRASE", PASSPHRASE)
    monkeypatch.setattr(cli_module, "REPO_DIR", str(tmp_path / "repo"))
    monkeypatch.setattr(os, "geteuid", lambda: 1000)

    class Runner:
        secrets = home / "secrets.enc"
        backups = home / "backups"
        legacy_json = tmp_path / "repo" / "json" / "secrets.json"

        def run(self, *argv, answers=()):
            replies = iter(answers)
            monkeypatch.setattr("builtins.input", lambda prompt="": next(replies))
            capsys.readouterr()
            code = cli_module.main(list(argv))
            out, err = capsys.readouterr()
            return code, out, err

        def store(self, accounts, passphrase=PASSPHRASE):
            vault.Vault(str(self.secrets), passphrase).save(accounts)

        def load(self, passphrase=PASSPHRASE):
            return vault.Vault(str(self.secrets), passphrase).load()

    return Runner()
