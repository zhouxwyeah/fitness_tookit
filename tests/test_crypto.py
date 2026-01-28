# tests/test_crypto.py
import pytest
from fitness_toolkit.crypto import encrypt_password, decrypt_password


def test_encrypt_decrypt_roundtrip():
    """Test that encryption and decryption are inverse operations."""
    password = "test_password_123"
    encrypted = encrypt_password(password)
    decrypted = decrypt_password(encrypted)
    assert decrypted == password


def test_encrypt_empty_password():
    """Test that empty password returns None."""
    result = encrypt_password("")
    assert result is None


def test_decrypt_empty_password():
    """Test that empty encrypted password returns None."""
    result = decrypt_password("")
    assert result is None
