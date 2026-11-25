"""Vault: secrets in the OS keyring (Windows Credential Manager, Secret Service/KWallet on Linux).
Instead of Touch ID, each use asks for a vault password (PBKDF2 hash in the config; the password itself is never stored)."""
import base64
import hashlib
import hmac
import json
import os
import time

SERVICE, ACCOUNT = "local.localwriter.vault", "vault"


def _keyring():
    import keyring
    return keyring


def keyring_available() -> bool:
    try:
        from keyring.backends.fail import Keyring as Fail
        return not isinstance(_keyring().get_keyring(), Fail)
    except Exception:  # noqa: BLE001
        return False


def load() -> dict[str, str]:
    try:
        raw = _keyring().get_password(SERVICE, ACCOUNT)
        return json.loads(raw) if raw else {}
    except Exception:  # noqa: BLE001
        return {}


def save(d: dict[str, str]) -> bool:
    try:
        _keyring().set_password(SERVICE, ACCOUNT, json.dumps(d))
        return True
    except Exception:  # noqa: BLE001
        return False


def hash_password(pw: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 300_000)
    return "pbkdf2$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def check_password(pw: str, stored: str | None) -> bool:
    if not stored: return False
    try:
        _, s, h = stored.split("$")
        return hmac.compare_digest(hash_password(pw, base64.b64decode(s)).split("$")[2], h)
    except ValueError:
        return False


class Lock:
    def __init__(self):
        self.unlocked_until = 0.0

    @property
    def is_unlocked(self) -> bool:
        return time.time() < self.unlocked_until

    def unlock_for(self, seconds: float):
        self.unlocked_until = time.time() + seconds

    def lock(self):
        self.unlocked_until = 0.0
