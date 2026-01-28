"""Garmin Connect China client implementation."""

import logging
import time
from datetime import date
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests
import garth

from fitness_toolkit.clients.base import BaseClient
from fitness_toolkit.config import Config

logger = logging.getLogger(__name__)


class GarminClient(BaseClient):
    """Client for Garmin Connect China."""
    
    def __init__(self):
        super().__init__()
        self.domain = "garmin.cn"
        self.base_url = "https://connectapi.garmin.cn"
        garth.configure(domain=self.domain)
    
    def login(self, email: str, password: str) -> bool:
        """Authenticate with Garmin Connect China."""
        try:
            garth.login(email, password)
            self.authenticated = True
            logger.info(f"Successfully logged in as {email}")
            return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def get_activities(self, start_date: date, end_date: date, activity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get activities within date range."""
        if not self.authenticated:
            raise ValueError("Not authenticated. Call login() first.")
        
        activities = []
        start = 0
        limit = 100
        
        try:
            while True:
                # Use garth.connectapi() which is the correct API
                endpoint = "/activitylist-service/activities/search/activities"
                params = {
                    "start": start,
                    "limit": limit,
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat()
                }
                
                if activity_type:
                    params["activityType"] = activity_type
                
                # garth.connectapi() handles the base URL and authentication
                batch = garth.connectapi(endpoint, params=params)
                
                if not batch:
                    break
                
                activities.extend(batch)
                start += limit
                
                # Rate limiting
                time.sleep(Config.RATE_LIMIT_DELAY)
                
                if len(batch) < limit:
                    break
            
            logger.info(f"Retrieved {len(activities)} activities")
            return activities
            
        except Exception as e:
            logger.error(f"Failed to get activities: {e}")
            raise
    
    def download_activity(self, activity_id: str, format: str, save_path: Path) -> Optional[Path]:
        """Download an activity file."""
        if not self.authenticated:
            raise ValueError("Not authenticated. Call login() first.")
        
        format = format.lower()
        if format not in ['tcx', 'gpx', 'fit']:
            raise ValueError(f"Unsupported format: {format}")
        
        try:
            # Use garth.download() for downloading files
            endpoint = f"/download-service/export/{format}/activity/{activity_id}"
            response = garth.client.download(endpoint)
            
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(save_path, 'wb') as f:
                f.write(response)
            
            logger.info(f"Downloaded activity {activity_id} to {save_path}")
            return save_path
            
        except Exception as e:
            logger.error(f"Failed to download activity {activity_id}: {e}")
            return None
