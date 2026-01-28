"""Download service - simplified for personal tool."""

import logging
import time
from datetime import date
from pathlib import Path
from typing import Optional

from fitness_toolkit.config import Config
from fitness_toolkit.database import add_download_history
from fitness_toolkit.services.account import AccountService

logger = logging.getLogger(__name__)


class DownloadService:
    """Service for downloading activities from platforms."""
    
    def __init__(self):
        self.account_service = AccountService()
    
    def download(
        self,
        platform: str,
        start_date: date,
        end_date: date,
        file_format: str = 'tcx',
        activity_type: Optional[str] = None
    ) -> dict:
        """Download activities for a platform."""
        client = self.account_service.get_client(platform)
        if not client:
            raise ValueError(f"{platform} not configured or authentication failed")
        
        # Get activities
        activities = self._get_activities_with_retry(
            client, platform, start_date, end_date, activity_type
        )
        
        logger.info(f"Found {len(activities)} activities to download from {platform}")
        
        downloaded = []
        skipped = []
        failed = []
        
        for activity in activities:
            try:
                result = self._download_single_activity(
                    client, platform, activity, file_format
                )
                
                if result['status'] == 'downloaded':
                    downloaded.append(result)
                elif result['status'] == 'skipped':
                    skipped.append(result)
                else:
                    failed.append(result)
                    
            except Exception as e:
                logger.error(f"Failed to download activity: {e}")
                failed.append({'activity': activity, 'error': str(e)})
        
        return {
            'total': len(activities),
            'downloaded': len(downloaded),
            'skipped': len(skipped),
            'failed': len(failed),
            'details': {
                'downloaded': downloaded,
                'skipped': skipped,
                'failed': failed
            }
        }
    
    def _get_activities_with_retry(self, client, platform, start_date, end_date, activity_type):
        """Get activities with retry logic."""
        for attempt in range(Config.MAX_RETRY_COUNT):
            try:
                if platform == 'garmin':
                    return client.get_activities(start_date, end_date, activity_type)
                elif platform == 'coros':
                    sport_types = [activity_type] if activity_type else None
                    return client.get_activities(start_date, end_date, sport_types)
            except Exception as e:
                logger.warning(f"Failed to get activities (attempt {attempt + 1}): {e}")
                if attempt < Config.MAX_RETRY_COUNT - 1:
                    time.sleep(Config.RETRY_DELAY_BASE * (2 ** attempt))
                else:
                    raise
    
    def _download_single_activity(self, client, platform, activity, file_format):
        """Download a single activity."""
        # Extract activity info based on platform
        if platform == 'garmin':
            activity_id = str(activity.get('activityId'))
            activity_type = activity.get('activityType', {}).get('typeKey', 'unknown')
        elif platform == 'coros':
            activity_id = activity.get('labelId')
            activity_type = activity.get('sportType', 'unknown')
        else:
            raise ValueError(f"Unknown platform: {platform}")
        
        # Create save path
        save_dir = Path(Config.DOWNLOADS_DIR) / platform / str(activity_type)
        save_path = save_dir / f"{activity_id}.{file_format}"
        
        # Skip if already exists
        if save_path.exists():
            logger.info(f"Skipping {activity_id}, already exists")
            return {
                'activity_id': activity_id,
                'status': 'skipped',
                'reason': 'file_exists',
                'path': str(save_path)
            }
        
        # Download with retry
        for attempt in range(Config.MAX_RETRY_COUNT):
            try:
                if platform == 'garmin':
                    result = client.download_activity(activity_id, file_format, save_path)
                elif platform == 'coros':
                    sport_type = activity.get('sportType', 0)
                    result = client.download_activity(activity_id, sport_type, file_format, save_path)
                
                if result:
                    add_download_history(
                        platform=platform,
                        activity_id=activity_id,
                        activity_type=str(activity_type),
                        file_path=str(save_path),
                        file_format=file_format
                    )
                    
                    logger.info(f"Downloaded {activity_id}")
                    return {
                        'activity_id': activity_id,
                        'status': 'downloaded',
                        'path': str(save_path)
                    }
                else:
                    raise Exception("Download returned None")
                    
            except Exception as e:
                logger.warning(f"Download failed (attempt {attempt + 1}): {e}")
                if attempt < Config.MAX_RETRY_COUNT - 1:
                    time.sleep(Config.RETRY_DELAY_BASE * (2 ** attempt))
                else:
                    raise
        
        return {
            'activity_id': activity_id,
            'status': 'failed',
            'error': 'Max retries exceeded'
        }
