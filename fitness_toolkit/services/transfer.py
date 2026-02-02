import logging
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional, List, Dict, Any

from fitness_toolkit.clients.coros import CorosClient
from fitness_toolkit.clients.garmin import GarminClient
from fitness_toolkit.config import Config
from fitness_toolkit.services.account import AccountService

logger = logging.getLogger(__name__)


class TransferService:
    def __init__(self):
        self.account_service = AccountService()

    def transfer(
        self,
        start_date: date,
        end_date: date,
        sport_types: Optional[List[str]] = None,
        save_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        coros_client = self.account_service.get_client("coros")
        garmin_client = self.account_service.get_client("garmin")

        if not coros_client:
            raise ValueError("COROS not configured or authentication failed")
        if not garmin_client:
            raise ValueError("Garmin not configured or authentication failed")

        if save_dir is None:
            save_dir = Path(tempfile.mkdtemp(prefix="coros_to_garmin_"))
        else:
            save_dir = Path(save_dir)
            save_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Transferring activities from {start_date} to {end_date}")
        if sport_types:
            logger.info(f"Filtering by sport types: {sport_types}")

        activities = coros_client.get_activities(start_date, end_date, sport_types)
        logger.info(f"Found {len(activities)} activities on COROS")

        results = {
            "total": len(activities),
            "downloaded": 0,
            "uploaded": 0,
            "skipped": 0,
            "failed": [],
            "activities": [],
        }

        for activity in activities:
            activity_result = self._transfer_single_activity(
                coros_client, garmin_client, activity, save_dir
            )
            results["activities"].append(activity_result)

            if activity_result["status"] == "success":
                results["downloaded"] += 1
                results["uploaded"] += 1
            elif activity_result["status"] == "skipped":
                results["skipped"] += 1
            else:
                results["failed"].append(activity_result)

        logger.info(
            f"Transfer complete: {results['uploaded']} uploaded, "
            f"{results['skipped']} skipped, {len(results['failed'])} failed"
        )

        return results

    def _transfer_single_activity(
        self,
        coros_client: CorosClient,
        garmin_client: GarminClient,
        activity: Dict[str, Any],
        save_dir: Path,
    ) -> Dict[str, Any]:
        label_id = activity.get("labelId", "")
        sport_type = activity.get("sportType", 0)
        activity_name = activity.get("name", f"Activity {label_id}")
        activity_time = activity.get("startTime", "")

        result = {
            "label_id": label_id,
            "name": activity_name,
            "time": activity_time,
            "status": "pending",
            "local_path": None,
            "garmin_id": None,
            "error": None,
        }

        try:
            fit_path = save_dir / f"{label_id}.fit"

            if fit_path.exists():
                logger.info(f"Using existing file: {fit_path}")
                result["local_path"] = str(fit_path)
            else:
                logger.info(f"Downloading activity {label_id}: {activity_name}")
                downloaded = coros_client.download_activity(
                    label_id, sport_type, "fit", fit_path
                )
                if not downloaded:
                    result["status"] = "failed"
                    result["error"] = "Download failed"
                    return result
                result["local_path"] = str(downloaded)

            logger.info(f"Uploading {label_id} to Garmin")
            garmin_id = garmin_client.upload_fit(
                fit_path,
                activity_name,
                start_time=activity_time,
            )

            if garmin_id == "duplicate":
                result["status"] = "skipped"
                result["garmin_id"] = garmin_id
            elif garmin_id:
                result["status"] = "success"
                result["garmin_id"] = garmin_id
            else:
                result["status"] = "failed"
                result["error"] = "Upload failed"

        except Exception as e:
            logger.error(f"Failed to transfer activity {label_id}: {e}")
            result["status"] = "failed"
            result["error"] = str(e)

        return result
