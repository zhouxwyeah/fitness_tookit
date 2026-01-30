# tests/test_crypto.py
import pytest

from fitness_toolkit.crypto import decrypt_password, encrypt_password


@pytest.fixture(autouse=True)
def consistent_encryption_key(monkeypatch):
    """Ensure consistent encryption key for all crypto tests."""
    # Generate a valid Fernet key
    from cryptography.fernet import Fernet

    test_key = Fernet.generate_key().decode()

    # Mock the Config to return our test key
    import fitness_toolkit.config as config_module

    original_key = config_module.Config.ENCRYPTION_KEY
    config_module.Config.ENCRYPTION_KEY = test_key

    yield test_key

    # Restore original key
    config_module.Config.ENCRYPTION_KEY = original_key


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


def test_encrypt_decrypt_special_characters():
    """Test encryption/decryption with special characters."""
    password = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
    encrypted = encrypt_password(password)
    decrypted = decrypt_password(encrypted)
    assert decrypted == password


def test_encrypt_decrypt_unicode():
    """Test encryption/decryption with unicode characters."""
    password = "测试密码123🚀"
    encrypted = encrypt_password(password)
    decrypted = decrypt_password(encrypted)
    assert decrypted == password
