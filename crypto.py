import base64
import hashlib

from cryptography.fernet import Fernet

import settings

_f = None


def _fernet() -> Fernet:
    global _f
    if _f is None:
        _f = Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.get("secret_key").encode()).digest()))
    return _f


def enc(s: str) -> str:
    return _fernet().encrypt(s.encode()).decode()


def dec(s: str) -> str:
    return _fernet().decrypt(s.encode()).decode()
