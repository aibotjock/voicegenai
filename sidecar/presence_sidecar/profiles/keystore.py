"""Key management for the encrypted profile store.

A voiceprint is biometric data (BIPA/IL-style exposure). The encryption key
lives in the OS keychain (macOS Keychain / Windows Credential Manager /
Linux Secret Service via `keyring`). When no keychain backend is available
(dev containers, CI), a file-based 0600 key is used and the app surfaces a
clear warning — never silent.
"""
from __future__ import annotations

import base64
import os
import warnings

from ..config import SETTINGS

SERVICE = "presence-studio"
ENTRY = "master-key"


class KeyStoreError(RuntimeError):
    pass


def _gen_key() -> bytes:
    from cryptography.fernet import Fernet
    return Fernet.generate_key()


def load_or_create_file_key() -> tuple[bytes, str]:
    key_path = SETTINGS.keys_dir / "master.key"
    if key_path.exists():
        key = base64.urlsafe_b64decode(key_path.read_bytes().strip())
    else:
        key = _gen_key()
        key_path.write_bytes(key)
        key_path.chmod(0o600)
    return key, str(key_path)


def get_master_key() -> tuple[bytes, str]:
    """Return (key, source). Prefers the OS keychain."""
    try:
        import keyring
        key = keyring.get_password(SERVICE, ENTRY)
        if key:
            return base64.urlsafe_b64decode(key.encode()), "keychain"
        new_key = _gen_key()
        keyring.set_password(SERVICE, ENTRY, base64.urlsafe_b64encode(new_key).decode())
        return new_key, "keychain"
    except Exception as e:  # no keychain backend in this environment
        key, path = load_or_create_file_key()
        warnings.warn(
            f"OS keychain unavailable ({e.__class__.__name__}); using file key at "
            f"{path} (0600). In production the key lives in the OS keychain.",
            stacklevel=2,
        )
        return key, "file"


def new_fernet() -> "object":
    from cryptography.fernet import Fernet
    key, _ = get_master_key()
    return Fernet(key)
