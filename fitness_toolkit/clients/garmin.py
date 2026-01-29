"""Garmin Connect China client implementation."""

import logging
import time
from datetime import date
from pathlib import Path
from typing import Optional, List, Dict, Any

import garth
from garth.exc import GarthHTTPError

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

    def upload_tcx(self, file_path: Path, activity_name: Optional[str] = None) -> Optional[str]:
        if not self.authenticated:
            raise ValueError("Not authenticated. Call login() first.")

        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        if file_path.suffix.lower() != ".tcx":
            logger.error(f"Invalid file format: {file_path.suffix}. Only TCX is supported.")
            return None

        try:
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f)}
                # Use request() directly with required headers for China endpoint
                response = garth.client.post(
                    "connectapi",
                    "/upload-service/upload",
                    api=True,
                    files=files,
                    headers={"nk": "NT"},
                )

            result = response.json()
            detailed_result = result.get("detailedImportResult", result)

            if len(detailed_result.get("successes", [])) == 0:
                failures = detailed_result.get("failures", [])
                if len(failures) > 0:
                    failure = failures[0]
                    if failure["messages"][0]["code"] == 202:
                        logger.warning("Activity already exists on Garmin")
                        return failure["internalId"]
                    else:
                        logger.error(f"Upload failed: {failure['messages']}")
                else:
                    logger.error("Unknown upload error")
                return None

            activity_id = detailed_result["successes"][0]["internalId"]
            logger.info(f"Successfully uploaded {file_path.name} as activity {activity_id}")

            if activity_name:
                self._set_activity_name(activity_id, activity_name)

            return activity_id

        except Exception as e:
            logger.error(f"Failed to upload {file_path}: {e}")
            return None

    def upload_fit(self, file_path: Path, activity_name: Optional[str] = None) -> Optional[str]:
        if not self.authenticated:
            raise ValueError("Not authenticated. Call login() first.")

        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        if file_path.suffix.lower() != ".fit":
            logger.error(f"Invalid file format: {file_path.suffix}. Only FIT is supported.")
            return None

        try:
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f)}
                response = garth.client.post(
                    "connectapi",
                    "/upload-service/upload",
                    api=True,
                    files=files,
                    headers={"nk": "NT"},
                )

            result = response.json()
            detailed_result = result.get("detailedImportResult", result)

            successes = detailed_result.get("successes", [])
            failures = detailed_result.get("failures", [])

            if len(successes) > 0:
                activity_id = successes[0]["internalId"]
                logger.info(f"Successfully uploaded {file_path.name} as activity {activity_id}")
                if activity_name:
                    self._set_activity_name(activity_id, activity_name)
                return activity_id

            if len(failures) > 0:
                failure = failures[0]
                messages = failure.get("messages", [])
                if messages and messages[0].get("code") == 202:
                    logger.warning("Activity already exists on Garmin")
                    return failure.get("internalId", "duplicate")
                else:
                    logger.error(f"Upload failed: {messages}")
                    return None

            logger.warning("Upload returned empty result - activity may be duplicate")
            return "duplicate"

        except GarthHTTPError as e:
            if "409" in str(e):
                logger.warning(f"Activity already exists on Garmin (409 Conflict)")
                return "duplicate"
            logger.error(f"Failed to upload {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to upload {file_path}: {e}")
            return None

    def _set_activity_name(self, activity_id: str, name: str) -> bool:
        try:
            path = f"/activity-service/activity/{activity_id}"
            data = {"activityId": activity_id, "activityName": name}
            garth.client.connectapi(path, method="PUT", json=data)
            return True

        except Exception as e:
            logger.warning(f"Failed to set activity name: {e}")
            return False
