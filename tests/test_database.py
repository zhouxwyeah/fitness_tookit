"""Tests for database module."""

import pytest
from fitness_toolkit.database import init_db, save_account, get_account, list_accounts
from fitness_toolkit.crypto import encrypt_password, decrypt_password

def test_init_db():
    """Test database initialization."""
    init_db()
    # Should not raise any exceptions


def test_save_and_get_account():
    """Test saving and retrieving an account."""
    save_account('garmin', 'zhouxwyeah@163.com', encrypt_password('Inter1908'))
    
    account = get_account('garmin')
    assert account is not None
    assert account['platform'] == 'garmin'
    assert account['email'] == 'test@example.com'


def test_list_accounts():
    """Test listing all accounts."""
    save_account('coros', '13564780117', encrypt_password('zzx141201'))
    accounts = list_accounts()
    
    assert len(accounts) >= 1
    platforms = [acc['platform'] for acc in accounts]
    assert 'garmin' in platforms
    assert 'coros' in platforms
