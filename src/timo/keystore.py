"""Remember the passphrase in the OS keychain (macOS Keychain, Linux Secret Service).

Every function here fails soft: if there is no keychain, it is locked, or it
is one of the "keyrings" that actually store passwords in a plain file, the
caller gets None/False and timo simply asks for the passphrase.
"""
import os

SERVICE = "timo"


def account_for(secrets_path):
    # one entry per secrets file, so separate stores (e.g. TIMO_HOME) don't clash
    return os.path.realpath(secrets_path)


def is_usable(backend):
    """True for real OS keychains; False for fail/null/plaintext backends."""
    module = type(backend).__module__
    if type(backend).__name__ == "ChainerBackend":
        members = list(getattr(backend, "backends", []))
        return bool(members) and all(is_usable(b) for b in members)
    if module.startswith("keyrings.alt") or module.endswith((".fail", ".null")):
        return False
    try:
        return backend.priority >= 1
    except Exception:
        return False


def _backend():
    try:
        import keyring
        backend = keyring.get_keyring()
    except Exception:
        return None
    return backend if is_usable(backend) else None


def get(secrets_path):
    backend = _backend()
    if backend is None:
        return None
    try:
        return backend.get_password(SERVICE, account_for(secrets_path))
    except Exception:
        return None


def set(secrets_path, passphrase):
    backend = _backend()
    if backend is None:
        return False
    try:
        backend.set_password(SERVICE, account_for(secrets_path), passphrase)
        return True
    except Exception:
        return False


def delete(secrets_path):
    backend = _backend()
    if backend is None:
        return False
    try:
        backend.delete_password(SERVICE, account_for(secrets_path))
        return True
    except Exception:
        return False
