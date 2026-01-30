"""Tests for database module."""

import tempfile
from pathlib import Path

import pytest

from fitness_toolkit.crypto import encrypt_password
from fitness_toolkit.database import (
    delete_account,
    get_account,
    init_db,
    list_accounts,
    save_account,
)


@pytest.fixture
def temp_db(monkeypatch):
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        # Mock the database path
        import fitness_toolkit.config as config_module
        import fitness_toolkit.database as db_module

        original_db_path = db_module.Config.DATABASE_PATH
        db_module.Config.DATABASE_PATH = db_path
        config_module.Config.DATABASE_PATH = db_path

        # Initialize the database
        init_db()

        yield db_path

        # Restore original path
        db_module.Config.DATABASE_PATH = original_db_path
        config_module.Config.DATABASE_PATH = original_db_path


def test_init_db(temp_db):
    """Test database initialization."""
    # Should not raise any exceptions
    init_db()
    assert temp_db.exists()


def test_save_and_get_account(temp_db):
    """Test saving and retrieving an account."""
    test_email = "test@example.com"
    test_password = "test_password_123"
    encrypted = encrypt_password(test_password)

    save_account("garmin", test_email, encrypted)

    account = get_account("garmin")
    assert account is not None
    assert account["platform"] == "garmin"
    assert account["email"] == test_email


def test_list_accounts(temp_db):
    """Test listing all accounts."""
    # Save test accounts
    save_account("garmin", "garmin@test.com", encrypt_password("garmin_pass"))
    save_account("coros", "coros@test.com", encrypt_password("coros_pass"))

    accounts = list_accounts()

    assert len(accounts) == 2
    platforms = [acc["platform"] for acc in accounts]
    assert "garmin" in platforms
    assert "coros" in platforms


def test_delete_account(temp_db):
    """Test deleting an account."""
    save_account("garmin", "test@example.com", encrypt_password("test_pass"))

    # Verify account exists
    account = get_account("garmin")
    assert account is not None

    # Delete account
    result = delete_account("garmin")
    assert result is True

    # Verify account is deleted
    account = get_account("garmin")
    assert account is None


def test_delete_nonexistent_account(temp_db):
    """Test deleting a non-existent account."""
    result = delete_account("nonexistent")
    assert result is False
