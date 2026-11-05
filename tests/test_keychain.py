import pytest

from conftest import PASSPHRASE
from totp_cli import commands, keystore

ACC = [{"issuer": "GitHub", "name": "me", "secret": "JBSWY3DPEHPK3PXP"}]


class FakeKeyring:
    priority = 5

    def __init__(self):
        self.items = {}

    def get_password(self, service, user):
        return self.items.get((service, user))

    def set_password(self, service, user, password):
        self.items[(service, user)] = password

    def delete_password(self, service, user):
        del self.items[(service, user)]


@pytest.fixture
def typed(monkeypatch):
    """Simulate typing at getpass prompts; records each prompt shown."""
    monkeypatch.delenv("TOTP_CLI_PASSPHRASE")
    prompts = []
    replies = []

    def fake_getpass(prompt=""):
        prompts.append(prompt)
        return replies.pop(0)

    monkeypatch.setattr(commands.getpass, "getpass", fake_getpass)
    return prompts, replies


@pytest.fixture
def keychain(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(keystore, "_backend", lambda: fake)
    return fake


def test_asks_once_then_uses_keychain(cli, typed, keychain):
    prompts, replies = typed
    cli.store(ACC)

    replies.append(PASSPHRASE)
    code, out, _ = cli.run("--list")
    assert code == 0 and len(prompts) == 1
    assert "saved in your keychain" in out

    code, out, _ = cli.run("--list")
    assert code == 0 and len(prompts) == 1  # not asked again
    assert "GitHub (me)" in out


def test_stale_keychain_passphrase_is_replaced(cli, typed, keychain):
    prompts, replies = typed
    cli.store(ACC)
    keychain.set_password(keystore.SERVICE, keystore.account_for(str(cli.secrets)), "old and wrong")

    replies.append(PASSPHRASE)
    code, out, _ = cli.run("--list")
    assert code == 0
    assert "no longer works" in out
    assert len(prompts) == 1
    assert keystore.get(str(cli.secrets)) == PASSPHRASE


def test_without_keychain_asks_every_time(cli, typed, monkeypatch):
    monkeypatch.setattr(keystore, "_backend", lambda: None)
    prompts, replies = typed
    cli.store(ACC)
    replies.extend([PASSPHRASE, PASSPHRASE])
    assert cli.run("--list")[0] == 0
    code, out, err = cli.run("--list")
    assert code == 0 and len(prompts) == 2
    assert "keychain" not in out + err


def test_env_passphrase_never_touches_keychain(cli, keychain):
    cli.store(ACC)
    assert cli.run("--list")[0] == 0
    assert keychain.items == {}


def test_broken_keychain_falls_back_to_prompt(cli, typed, monkeypatch):
    class Broken(FakeKeyring):
        def get_password(self, *a):
            raise RuntimeError("keychain locked")

        def set_password(self, *a):
            raise RuntimeError("keychain locked")

    monkeypatch.setattr(keystore, "_backend", lambda: Broken())
    prompts, replies = typed
    cli.store(ACC)
    replies.append(PASSPHRASE)
    code, out, _ = cli.run("--list")
    assert code == 0 and "GitHub (me)" in out


def test_forget_and_remember(cli, typed, keychain):
    prompts, replies = typed
    cli.store(ACC)
    replies.append(PASSPHRASE)
    cli.run("--list")
    assert keychain.items

    code, out, _ = cli.run("--forget")
    assert code == 0 and keychain.items == {}

    replies.append(PASSPHRASE)
    cli.run("--list")
    assert keychain.items == {}  # not saved again after forget

    code, out, _ = cli.run("--remember")
    assert code == 0
    replies.append(PASSPHRASE)
    cli.run("--list")
    assert keystore.get(str(cli.secrets)) == PASSPHRASE


def test_new_store_saves_passphrase(cli, typed, keychain, monkeypatch):
    prompts, replies = typed
    replies.extend(["first passphrase", "first passphrase"])
    cli.legacy_json.parent.mkdir(parents=True)
    cli.legacy_json.write_text('[{"issuer": "A", "name": "a", "secret": "JBSWY3DPEHPK3PXP"}]')
    code, out, _ = cli.run("--migrate", answers=["n"])
    assert code == 0
    assert keystore.get(str(cli.secrets)) == "first passphrase"


def test_passwd_updates_keychain(cli, typed, keychain, monkeypatch):
    prompts, replies = typed
    cli.store(ACC)
    replies.append(PASSPHRASE)
    cli.run("--list")
    monkeypatch.setattr(commands, "ask_new_passphrase", lambda: "a new passphrase")
    code, out, _ = cli.run("--passwd")
    assert code == 0
    assert keystore.get(str(cli.secrets)) == "a new passphrase"
    assert cli.load("a new passphrase") == ACC


# --- which backends count as a real keychain -------------------------------------

def make(module, name="Keyring", priority=5, **attrs):
    cls = type(name, (), {"priority": priority, "__module__": module, **attrs})
    return cls()


@pytest.mark.parametrize("backend, usable", [
    (make("keyring.backends.macOS"), True),
    (make("keyring.backends.SecretService"), True),
    (make("keyring.backends.fail", priority=0), False),
    (make("keyrings.alt.file", "PlaintextKeyring", priority=0.5), False),
    (make("keyrings.alt.file", "EncryptedKeyring", priority=5), False),
    (make("keyring.backends.null", priority=-1), False),
])
def test_usable_backends(backend, usable):
    assert keystore.is_usable(backend) is usable


def test_chainer_is_usable_only_without_insecure_members():
    good = make("keyring.backends.macOS")
    bad = make("keyrings.alt.file", "PlaintextKeyring", priority=0.5)
    assert keystore.is_usable(make("keyring.backends.chainer", "ChainerBackend", backends=[good]))
    assert not keystore.is_usable(make("keyring.backends.chainer", "ChainerBackend", backends=[good, bad]))
    assert not keystore.is_usable(make("keyring.backends.chainer", "ChainerBackend", backends=[]))
