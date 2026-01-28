"""Password encryption module using Fernet."""

import os
import logging
from cryptography.fernet import Fernet

from fitness_toolkit.config import Config

logger = logging.getLogger(__name__)


def get_or_create_key():
    """Get encryption key from environment or generate a new one."""
    key = Config.ENCRYPTION_KEY
    
    if key:
        return key.encode() if isinstance(key, str) else key
    
    # Generate new key
    key = Fernet.generate_key()
    logger.warning(
        "FITNESS_ENCRYPTION_KEY not set. A new key has been generated.\n"
        "Please save this key to your environment variables:\n"
        f"FITNESS_ENCRYPTION_KEY={key.decode()}"
    )
    return key


def get_fernet():
    """Get Fernet instance with the encryption key."""
    key = get_or_create_key()
    return Fernet(key)


def encrypt_password(password):
    """Encrypt a password string."""
    if not password:
        return None
    
    f = get_fernet()
    encrypted = f.encrypt(password.encode())
    return encrypted.decode()


def decrypt_password(encrypted_password):
    """Decrypt an encrypted password string."""
    if not encrypted_password:
        return None
    
    try:
        f = get_fernet()
        decrypted = f.decrypt(encrypted_password.encode())
        return decrypted.decode()
    except Exception as e:
        logger.error("Failed to decrypt password")
        raise ValueError("Invalid encryption key or corrupted data") from e
