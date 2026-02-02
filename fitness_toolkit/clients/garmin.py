"""Garmin Connect China client implementation.

This module uses per-instance garth.Client for thread safety when running
concurrent uploads.
"""

import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from garth import Client
from garth.exc import GarthHTTPError

from fitness_toolkit.clients.base import BaseClient
from fitness_toolkit.config import Config

logger = logging.getLogger(__name__)


class GarminClient(BaseClient):
    """Client for Garmin Connect China.
    
    Uses a per-instance garth.Client for thread safety.
    """

    def __init__(self):
        super().__init__()
        self.domain = "garmin.cn"
        self.base_url = "https://connectapi.garmin.cn"
        # Create per-instance client for thread safety
        self._client: Optional[Client] = None

    @property
    def client(self) -> Client:
        """Get the garth client, creating if needed."""
        if self._client is None:
            self._client = Client(domain=self.domain)
        return self._client

    def login(self, email: str, password: str) -> bool:
        """Authenticate with Garmin Connect China."""
        try:
            # Use per-instance client
            self.client.login(email, password)
            self.authenticated = True
            logger.info(f"Successfully logged in as {email}")
            return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    def get_activities(
        self, start_date: date, end_date: date, activity_type: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Get activities within date range."""
        if not self.authenticated:
            raise ValueError("Not authenticated. Call login() first.")

        activities = []
        start = 0
        limit = 100

        try:
            while True:
                endpoint = "/activitylist-service/activities/search/activities"
                params = {
                    "start": start,
                    "limit": limit,
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                }

                if activity_type:
                    params["activityType"] = activity_type

                batch = self.client.connectapi(endpoint, params=params)

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

    def download_activity(
        self, activity_id: str, format: str, save_path: Path
    ) -> Optional[Path]:
        """Download an activity file."""
        if not self.authenticated:
            raise ValueError("Not authenticated. Call login() first.")

        format = format.lower()
        if format not in ["tcx", "gpx", "fit"]:
            raise ValueError(f"Unsupported format: {format}")

        try:
            endpoint = f"/download-service/export/{format}/activity/{activity_id}"
            response = self.client.download(endpoint)

            save_path.parent.mkdir(parents=True, exist_ok=True)

            with open(save_path, "wb") as f:
                f.write(response)

            logger.info(f"Downloaded activity {activity_id} to {save_path}")
            return save_path

        except Exception as e:
            logger.error(f"Failed to download activity {activity_id}: {e}")
            return None

    def upload_tcx(
        self, file_path: Path, activity_name: Optional[str] = None
    ) -> Optional[str]:
        """Upload a TCX file to Garmin."""
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
                response = self.client.post(
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
                        return "duplicate"
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

    def upload_fit(
        self,
        file_path: Path,
        activity_name: Optional[str] = None,
        start_time: Any = None,
    ) -> Optional[str]:
        """Upload a FIT file to Garmin."""
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
                response = self.client.post(
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

            logger.warning(
                "Upload returned empty result; attempting duplicate confirmation"
            )

            confirmed = self._confirm_duplicate_by_time(start_time)
            if confirmed:
                logger.warning(
                    "Empty upload result confirmed as duplicate (matched existing activity)"
                )
                return confirmed

            logger.error(
                "Upload returned empty result and could not be confirmed as duplicate"
            )
            return None

        except GarthHTTPError as e:
            if "409" in str(e):
                logger.warning("Activity already exists on Garmin (409 Conflict)")
                return "duplicate"
            logger.error(f"Failed to upload {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to upload {file_path}: {e}")
            return None

    def _confirm_duplicate_by_time(self, start_time: Any) -> Optional[str]:
        """Best-effort confirm duplicates by searching Garmin activity list near start time."""
        if not start_time:
            return None

        start_dt = self._parse_coros_start_time(start_time)
        if not start_dt:
            return None

        window = timedelta(seconds=Config.DUPLICATE_CONFIRM_WINDOW_SECONDS)
        search_days = max(0, int(Config.DUPLICATE_CONFIRM_SEARCH_DAYS))

        start_date = (start_dt - timedelta(days=search_days)).date()
        end_date = (start_dt + timedelta(days=search_days)).date()

        try:
            activities = self.get_activities(start_date, end_date)
        except Exception as e:
            logger.warning(f"Failed to fetch Garmin activities for duplicate check: {e}")
            return None

        best_id = None
        best_delta = None

        for act in activities:
            act_start = self._parse_garmin_activity_start(act)
            if not act_start:
                continue
            delta = abs(act_start - start_dt)
            if delta <= window and (best_delta is None or delta < best_delta):
                best_delta = delta
                best_id = act.get("activityId") or act.get("internalId")

        return str(best_id) if best_id is not None else None

    def _parse_coros_start_time(self, value: Any) -> Optional[datetime]:
        """Parse COROS startTime (epoch seconds/ms, ISO string, or datetime) to datetime."""
        if isinstance(value, datetime):
            return value

        # epoch seconds/ms (int/float/str)
        try:
            if isinstance(value, (int, float)):
                ts = float(value)
            elif isinstance(value, str) and value.strip().isdigit():
                ts = float(value.strip())
            else:
                ts = None
            if ts is not None:
                # Heuristic: ms if too large
                if ts > 10_000_000_000:
                    ts = ts / 1000.0
                return datetime.fromtimestamp(ts)
        except Exception:
            pass

        if isinstance(value, str):
            s = value.strip()
            # common formats
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(s, fmt)
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                return None

        return None

    def _parse_garmin_activity_start(self, activity: dict[str, Any]) -> Optional[datetime]:
        """Parse Garmin activity start time from activity list item."""
        # Common keys seen in Garmin Connect APIs
        for key in ("startTimeLocal", "startTimeGMT", "beginTimestamp"):
            if key not in activity or activity[key] is None:
                continue
            v = activity[key]
            # beginTimestamp sometimes milliseconds
            if key == "beginTimestamp":
                try:
                    ts = float(v)
                    if ts > 10_000_000_000:
                        ts = ts / 1000.0
                    return datetime.fromtimestamp(ts)
                except Exception:
                    continue

            if isinstance(v, str):
                s = v.strip()
                # Garmin often uses: 2024-01-15 08:30:00
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        return datetime.strptime(s, fmt)
                    except ValueError:
                        continue
                try:
                    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(
                        tzinfo=None
                    )
                except ValueError:
                    continue
        return None

    def _set_activity_name(self, activity_id: str, name: str) -> bool:
        """Set the name of an activity."""
        try:
            path = f"/activity-service/activity/{activity_id}"
            data = {"activityId": activity_id, "activityName": name}
            self.client.connectapi(path, method="PUT", json=data)
            return True
        except Exception as e:
            logger.warning(f"Failed to set activity name: {e}")
            return False

    def set_activity_description(self, activity_id: str, description: str) -> bool:
        """Set the description of an activity."""
        try:
            path = f"/activity-service/activity/{activity_id}"
            data = {"activityId": activity_id, "description": description}
            self.client.connectapi(path, method="PUT", json=data)
            return True
        except Exception as e:
            logger.warning(f"Failed to set activity description: {e}")
            return False

    def set_activity_privacy(self, activity_id: str, visibility: str) -> bool:
        """Set activity privacy level.
        
        Args:
            activity_id: Garmin activity ID
            visibility: "private" or "public"
        """
        try:
            path = f"/activity-service/activity/{activity_id}"
            data = {"activityId": activity_id, "privacy": {"typeKey": visibility}}
            self.client.connectapi(path, method="PUT", json=data)
            return True
        except Exception as e:
            logger.warning(f"Failed to set privacy for {activity_id}: {e}")
            return False

    def link_gear(self, activity_id: str, gear_id: str) -> bool:
        """Link gear to an activity.
        
        Args:
            activity_id: Garmin activity ID
            gear_id: Gear UUID from /gear-service/gear/filterGear
        """
        try:
            path = f"/gear-service/gear/link/{gear_id}/activity/{activity_id}"
            self.client.connectapi(path, method="PUT")
            return True
        except Exception as e:
            logger.warning(f"Failed to link gear {gear_id} to activity {activity_id}: {e}")
            return False

    def get_gear(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get user's gear list."""
        try:
            gear_data = self.client.connectapi(
                "/gear-service/gear/filterGear",
                params={"start": 0, "limit": limit},
            )
            if gear_data and isinstance(gear_data, list):
                return [
                    {
                        "id": str(g.get("uuid", g.get("gearPk", ""))),
                        "name": g.get("displayName", g.get("customMakeModel", "Unknown")),
                        "type": g.get("gearTypeName", ""),
                    }
                    for g in gear_data
                ]
            return []
        except Exception as e:
            logger.warning(f"Failed to fetch Garmin gear: {e}")
            return []
