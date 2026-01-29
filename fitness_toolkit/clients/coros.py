"""COROS Training Hub client implementation."""

import hashlib
import logging
import re
import time
from datetime import date
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests

from fitness_toolkit.clients.base import BaseClient
from fitness_toolkit.config import Config

logger = logging.getLogger(__name__)

COROS_FILE_TYPES = {
    "gpx": 1,
    "fit": 4,
    "tcx": 3,
}


def fix_tcx_extensions(content: bytes) -> bytes:
    """Fix COROS TCX Extensions to be Garmin-compatible.
    
    COROS exports: <Extensions><Speed>X</Speed></Extensions>
    Garmin expects: <Extensions><ns3:TPX><ns3:Speed>X</ns3:Speed></ns3:TPX></Extensions>
    """
    text = content.decode("utf-8")
    
    pattern = r'<Extensions>\s*<Speed>([^<]+)</Speed>\s*</Extensions>'
    replacement = r'<Extensions><ns3:TPX><ns3:Speed>\1</ns3:Speed></ns3:TPX></Extensions>'
    
    fixed = re.sub(pattern, replacement, text)
    return fixed.encode("utf-8")


class CorosClient(BaseClient):
    """Client for COROS Training Hub."""
    
    def __init__(self):
        super().__init__()
        self.base_url = "https://teamcnapi.coros.com"
        self.session = requests.Session()
        self.access_token = None
        self.user_id = None
    
    def _hash_password(self, password: str) -> str:
        """Hash password using MD5."""
        return hashlib.md5(password.encode()).hexdigest()
    
    def login(self, account: str, password: str) -> bool:
        """Authenticate with COROS."""
        try:
            url = f"{self.base_url}/account/login"
            payload = {
                "account": account,
                "accountType": 2,
                "pwd": self._hash_password(password)
            }
            
            response = self.session.post(url, json=payload, timeout=Config.REQUEST_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("result") == "0000":
                self.access_token = data["data"]["accessToken"]
                self.user_id = data["data"]["userId"]
                self.authenticated = True
                
                # Set auth headers for future requests
                self.session.headers.update({
                    "accesstoken": self.access_token
                })
                
                logger.info(f"Successfully logged in as {account}")
                return True
            else:
                logger.error(f"Login failed: {data.get('message', 'Unknown error')}")
                return False
                
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def get_activities(self, start_date: date, end_date: date, sport_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get activities within date range."""
        if not self.authenticated:
            raise ValueError("Not authenticated. Call login() first.")

        activities = []
        page = 1
        size = 20

        try:
            while True:
                url = f"{self.base_url}/activity/query"
                params = {
                    "pageNumber": page,
                    "size": size,
                    "startDay": start_date.strftime("%Y%m%d"),
                    "endDay": end_date.strftime("%Y%m%d"),
                    "modeList": ",".join(sport_types) if sport_types else ""
                }

                response = self.session.get(url, params=params, timeout=Config.REQUEST_TIMEOUT)
                response.raise_for_status()

                data = response.json()

                if data.get("result") != "0000":
                    logger.error(f"Failed to get activities: {data.get('message')}")
                    break

                batch = data["data"]["dataList"]
                if not batch:
                    break

                activities.extend(batch)
                page += 1

                # Rate limiting
                time.sleep(Config.RATE_LIMIT_DELAY)

                if len(batch) < size:
                    break

            logger.info(f"Retrieved {len(activities)} activities")
            return activities

        except Exception as e:
            logger.error(f"Failed to get activities: {e}")
            raise
    
    def download_activity(self, label_id: str, sport_type: int, file_format: str, save_path: Path) -> Optional[Path]:
        """Download an activity file."""
        if not self.authenticated:
            raise ValueError("Not authenticated. Call login() first.")
        
        file_type = COROS_FILE_TYPES.get(str(file_format).lower())
        if not file_type:
            logger.error(f"Unsupported file format: {file_format}")
            return None
        
        try:
            url = f"{self.base_url}/activity/detail/download"
            params = {
                "labelId": label_id,
                "sportType": sport_type,
                "fileType": file_type
            }
            
            response = self.session.post(url, params=params, timeout=Config.REQUEST_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("result") != "0000":
                logger.error(f"Failed to get download URL: {data.get('message')}")
                return None
            
            file_url = data.get("data", {}).get("fileUrl")
            if not file_url:
                logger.error(f"No file URL in response: {data}")
                return None
            
            file_response = self.session.get(file_url, timeout=Config.REQUEST_TIMEOUT)
            file_response.raise_for_status()
            
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            content = file_response.content
            if file_format.lower() == "tcx":
                content = fix_tcx_extensions(content)
            
            with open(save_path, 'wb') as f:
                f.write(content)
            
            logger.info(f"Downloaded activity {label_id} to {save_path}")
            return save_path
            
        except Exception as e:
            logger.error(f"Failed to download activity {label_id}: {e}")
            return None
