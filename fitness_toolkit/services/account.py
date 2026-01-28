"""Account management service - simplified for personal tool."""

import logging
from typing import Optional, Dict, Any

from fitness_toolkit.database import (
    save_account as db_save_account,
    get_account as db_get_account,
    list_accounts as db_list_accounts,
    delete_account as db_delete_account,
    has_account as db_has_account
)
from fitness_toolkit.crypto import encrypt_password, decrypt_password
from fitness_toolkit.clients.garmin import GarminClient
from fitness_toolkit.clients.coros import CorosClient

logger = logging.getLogger(__name__)


class AccountService:
    """Service for managing platform accounts (one per platform)."""
    
    def __init__(self):
        self._clients = {}
    
    def configure(self, platform: str, email: str, password: str):
        """Configure account for a platform."""
        encrypted_password = encrypt_password(password)
        db_save_account(platform, email, encrypted_password)
        logger.info(f"Configured {platform} account for {email}")
    
    def list_accounts(self) -> list:
        """List all configured accounts with status."""
        accounts = db_list_accounts()
        for acc in accounts:
            acc['is_configured'] = True
        return accounts
    
    def get_account(self, platform: str) -> Optional[Dict[str, Any]]:
        """Get account by platform name."""
        return db_get_account(platform)
    
    def remove_account(self, platform: str) -> bool:
        """Remove account for a platform."""
        result = db_delete_account(platform)
        if result:
            logger.info(f"Removed {platform} configuration")
            if platform in self._clients:
                del self._clients[platform]
        return result
    
    def is_configured(self, platform: str) -> bool:
        """Check if platform has a configured account."""
        return db_has_account(platform)
    
    def verify(self, platform: str) -> bool:
        """Verify account credentials for a platform."""
        account = self.get_account(platform)
        if not account:
            logger.error(f"{platform} not configured")
            return False
        
        email = account['email']
        password = decrypt_password(account['password_encrypted'])
        
        try:
            if platform == 'garmin':
                client = GarminClient()
                success = client.login(email, password)
            elif platform == 'coros':
                client = CorosClient()
                success = client.login(email, password)
            else:
                logger.error(f"Unknown platform: {platform}")
                return False
            
            if success:
                self._clients[platform] = client
                logger.info(f"Successfully verified {platform} account")
            else:
                logger.error(f"Failed to verify {platform} account")
            
            return success
            
        except Exception as e:
            logger.error(f"Error verifying {platform}: {e}")
            return False
    
    def get_client(self, platform: str):
        """Get authenticated client for a platform."""
        if platform in self._clients:
            return self._clients[platform]
        
        if self.verify(platform):
            return self._clients.get(platform)
        
        return None
