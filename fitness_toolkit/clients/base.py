"""Base client interface for fitness platforms."""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import date
from pathlib import Path


class BaseClient(ABC):
    """Abstract base class for fitness platform clients."""
    
    def __init__(self):
        self.authenticated = False
        self.token = None
    
    @abstractmethod
    def login(self, email: str, password: str) -> bool:
        """Authenticate with the platform."""
        pass
    
    @abstractmethod
    def get_activities(self, start_date: date, end_date: date, activity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get activities within date range."""
        pass
    
    @abstractmethod
    def download_activity(self, activity_id: str, format: str, save_path: Path) -> Optional[Path]:
        """Download an activity file."""
        pass
