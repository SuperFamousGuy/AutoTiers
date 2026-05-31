"""Fernet (AES) encryption helpers for at-rest secrets like OAuth cookies.

The key is configured via Settings.secret_key — base64-urlsafe 32 bytes.
"""
from cryptography.fernet import Fernet, InvalidToken
from app.config import settings


class InvalidCiphertext(Exception):
    """Raised when ciphertext is missing, malformed, or has a bad signature."""


def _fernet() -> Fernet:
    return Fernet(settings.secret_key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise InvalidCiphertext("Ciphertext is invalid or signature failed") from e
