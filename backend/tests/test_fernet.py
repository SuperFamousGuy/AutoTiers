import pytest
from app.security.fernet import encrypt, decrypt, InvalidCiphertext


def test_round_trip_returns_original_plaintext():
    secret = "my-cookie-value-12345"
    ciphertext = encrypt(secret)
    assert ciphertext != secret  # actually encrypted
    assert decrypt(ciphertext) == secret


def test_decrypt_rejects_tampered_ciphertext():
    ciphertext = encrypt("payload")
    tampered = ciphertext[:-2] + "AA"
    with pytest.raises(InvalidCiphertext):
        decrypt(tampered)


def test_encrypt_outputs_are_nondeterministic():
    """Fernet includes a random IV — repeated calls yield different ciphertexts."""
    assert encrypt("same") != encrypt("same")
