"""Transfer worker service - background job processing for COROS->Garmin sync."""

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Optional

from fitness_toolkit.clients.coros import CorosClient
from fitness_toolkit.clients.garmin import GarminClient
from fitness_toolkit.config import Config
from fitness_toolkit.crypto import decrypt_password
from fitness_toolkit.database import get_account
from fitness_toolkit.services.account import AccountService
from fitness_toolkit.services.transfer_queue import (
    ITEM_STATUS_DOWNLOADING,
    ITEM_STATUS_FAILED,
    ITEM_STATUS_PENDING,
    ITEM_STATUS_SKIPPED,
    ITEM_STATUS_SUCCESS,
    ITEM_STATUS_UPLOADING,
    JOB_STATUS_CANCELLED,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PAUSED,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    METADATA_STATUS_FAILED,
    METADATA_STATUS_SKIPPED,
    METADATA_STATUS_SUCCESS,
    TransferQueueService,
)
from fitness_toolkit.services.transfer_settings import (
    COROS_SPORT_NAMES,
    TemplateRenderer,
    TransferSettingsService,
)

logger = logging.getLogger(__name__)


class TransferWorker:
    """Background worker for processing transfer jobs."""

    def __init__(
        self,
        queue_service: Optional[TransferQueueService] = None,
        account_service: Optional[AccountService] = None,
        settings_service: Optional[TransferSettingsService] = None,
    ):
        self.queue_service = queue_service or TransferQueueService()
        self.account_service = account_service or AccountService()
        self.settings_service = settings_service or TransferSettingsService()

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._current_job_id: Optional[int] = None
        self._lock = threading.Lock()

        # Callbacks for status updates
        self._on_item_complete: Optional[Callable[[int, dict], None]] = None
        self._on_job_complete: Optional[Callable[[int, dict], None]] = None

    @property
    def is_running(self) -> bool:
        """Check if worker thread is running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_paused(self) -> bool:
        """Check if worker is paused."""
        return self._pause_event.is_set()

    @property
    def current_job_id(self) -> Optional[int]:
        """Get the current job being processed."""
        return self._current_job_id

    def start(self) -> bool:
        """Start the worker thread."""
        if self.is_running:
            logger.warning("Worker is already running")
            return False

        self._stop_event.clear()
        self._pause_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        logger.info("Transfer worker started")
        return True

    def stop(self, wait: bool = True, timeout: float = 10.0) -> bool:
        """Stop the worker thread."""
        if not self.is_running:
            return True

        self._stop_event.set()
        self._pause_event.clear()  # Unpause so thread can exit

        if wait and self._thread:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("Worker thread did not stop within timeout")
                return False

        logger.info("Transfer worker stopped")
        return True

    def pause(self) -> bool:
        """Pause the worker (finish current item, then wait)."""
        if not self.is_running:
            return False

        self._pause_event.set()
        logger.info("Transfer worker paused")

        # Update current job status if any
        if self._current_job_id:
            self.queue_service.update_job_status(self._current_job_id, JOB_STATUS_PAUSED)

        return True

    def resume(self) -> bool:
        """Resume the worker from paused state."""
        if not self.is_running:
            return False

        if self._current_job_id:
            self.queue_service.update_job_status(self._current_job_id, JOB_STATUS_RUNNING)

        self._pause_event.clear()
        logger.info("Transfer worker resumed")
        return True

    def process_job(self, job_id: int) -> bool:
        """
        Queue a job for processing.

        If worker is running, the job will be picked up automatically.
        If not running, starts the worker.
        """
        job = self.queue_service.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return False

        if job["status"] not in (JOB_STATUS_PENDING, JOB_STATUS_PAUSED):
            logger.warning(f"Job {job_id} is not in pending/paused state: {job['status']}")
            return False

        # Mark as pending to be picked up
        self.queue_service.update_job_status(job_id, JOB_STATUS_PENDING)

        if not self.is_running:
            self.start()

        return True

    def _worker_loop(self) -> None:
        """Main worker loop - processes jobs sequentially."""
        logger.info("Worker loop started")

        while not self._stop_event.is_set():
            # Check for pause
            while self._pause_event.is_set() and not self._stop_event.is_set():
                time.sleep(0.5)

            if self._stop_event.is_set():
                break

            # Find next pending job
            job = self._get_next_job()
            if not job:
                # No work to do, sleep before checking again
                time.sleep(1.0)
                continue

            # Process the job
            self._process_single_job(job)

        logger.info("Worker loop ended")

    def _get_next_job(self) -> Optional[dict[str, Any]]:
        """Get the next pending job to process."""
        jobs = self.queue_service.list_jobs(limit=10)
        for job in jobs:
            if job["status"] == JOB_STATUS_PENDING:
                return self.queue_service.get_job(job["id"])
        return None

    def _create_garmin_client(self) -> Optional[GarminClient]:
        """Create a new authenticated Garmin client (thread-safe)."""
        account = get_account("garmin")
        if not account:
            return None
        
        email = account["email"]
        password = decrypt_password(account["password_encrypted"])
        if not password:
            return None
        
        client = GarminClient()
        if client.login(email, password):
            return client
        return None

    def _create_coros_client(self) -> Optional[CorosClient]:
        """Create a new authenticated COROS client."""
        account = get_account("coros")
        if not account:
            return None
        
        email = account["email"]
        password = decrypt_password(account["password_encrypted"])
        if not password:
            return None
        
        client = CorosClient()
        if client.login(email, password):
            return client
        return None

    def _process_single_job(self, job: dict[str, Any]) -> None:
        """Process a single job with concurrent item processing."""
        job_id = job["id"]
        self._current_job_id = job_id

        logger.info(f"Starting job {job_id}")
        self.queue_service.update_job_status(job_id, JOB_STATUS_RUNNING)

        # Get settings from snapshot
        settings = job.get("settings_snapshot", {})
        concurrency = settings.get("concurrency", 2)
        retry_config = settings.get("retry", {})
        max_attempts = retry_config.get("max_attempts", 3)
        base_delay = retry_config.get("base_delay_seconds", 1)
        max_delay = retry_config.get("max_delay_seconds", 60)

        # Create initial clients to verify credentials
        coros_client = self._create_coros_client()
        garmin_client = self._create_garmin_client()

        if not coros_client or not garmin_client:
            error = "Failed to authenticate with COROS or Garmin"
            logger.error(error)
            self.queue_service.update_job_status(job_id, JOB_STATUS_FAILED, error_message=error)
            self._current_job_id = None
            return

        # Process items with ThreadPoolExecutor
        try:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                while not self._stop_event.is_set():
                    # Check for pause
                    if self._pause_event.is_set():
                        logger.info(f"Job {job_id} paused")
                        break

                    # Get batch of pending items
                    items = self.queue_service.get_pending_items(job_id, limit=concurrency)
                    if not items:
                        # No more items
                        break

                    # Submit items for processing
                    futures = {}
                    for item in items:
                        # Mark as in-progress before submitting
                        self.queue_service.update_item_status(item["id"], ITEM_STATUS_DOWNLOADING)
                        
                        future = executor.submit(
                            self._process_item_concurrent,
                            item,
                            settings,
                            max_attempts,
                            base_delay,
                            max_delay,
                        )
                        futures[future] = item["id"]

                    # Wait for batch to complete
                    for future in as_completed(futures):
                        item_id = futures[future]
                        try:
                            future.result()
                        except Exception as e:
                            logger.exception(f"Item {item_id} failed with exception: {e}")

                        # Check for stop/pause after each item
                        if self._stop_event.is_set() or self._pause_event.is_set():
                            break

                    # Update job counts after batch
                    self.queue_service.update_job_counts(job_id)

            # Check final status
            if self._stop_event.is_set():
                logger.info(f"Job {job_id} stopped by worker shutdown")
            elif self._pause_event.is_set():
                # Already set to paused above
                pass
            else:
                # Job completed
                counts = self.queue_service.update_job_counts(job_id)
                if counts["failed_count"] > 0 and counts["success_count"] == 0:
                    self.queue_service.update_job_status(job_id, JOB_STATUS_FAILED)
                else:
                    self.queue_service.update_job_status(job_id, JOB_STATUS_COMPLETED)
                logger.info(
                    f"Job {job_id} completed: {counts['success_count']} success, "
                    f"{counts['skipped_count']} skipped, {counts['failed_count']} failed"
                )

                if self._on_job_complete:
                    updated_job = self.queue_service.get_job(job_id)
                    if updated_job:
                        self._on_job_complete(job_id, updated_job)

        except Exception as e:
            logger.exception(f"Error processing job {job_id}: {e}")
            self.queue_service.update_job_status(job_id, JOB_STATUS_FAILED, error_message=str(e))

        finally:
            self._current_job_id = None

    def _process_item_concurrent(
        self,
        item: dict[str, Any],
        settings: dict[str, Any],
        max_attempts: int,
        base_delay: float,
        max_delay: float,
    ) -> None:
        """Process a single item in a worker thread (creates own clients)."""
        # Create thread-local clients
        coros_client = self._create_coros_client()
        garmin_client = self._create_garmin_client()

        if not coros_client or not garmin_client:
            self.queue_service.update_item_status(
                item["id"],
                ITEM_STATUS_FAILED,
                error_message="Failed to create clients",
            )
            return

        self._process_single_item(
            item,
            coros_client,
            garmin_client,
            settings,
            max_attempts,
            base_delay,
            max_delay,
        )

    def _process_single_item(
        self,
        item: dict[str, Any],
        coros_client: CorosClient,
        garmin_client: GarminClient,
        settings: dict[str, Any],
        max_attempts: int,
        base_delay: float,
        max_delay: float,
    ) -> None:
        """Process a single transfer item with retry logic."""
        item_id = item["id"]
        label_id = item["label_id"]
        sport_type = item["sport_type"]
        activity_name = item["activity_name"]

        logger.info(f"Processing item {item_id}: {label_id} ({activity_name})")

        # Retry loop
        attempt = item.get("retry_count", 0)
        last_error = None

        while attempt < max_attempts:
            if self._stop_event.is_set() or self._pause_event.is_set():
                return

            try:
                # Step 1: Download from COROS
                self.queue_service.update_item_status(item_id, ITEM_STATUS_DOWNLOADING)

                save_dir = Path(Config.DOWNLOADS_DIR) / "coros" / str(sport_type)
                fit_path = save_dir / f"{label_id}.fit"

                if not fit_path.exists():
                    downloaded = coros_client.download_activity(
                        label_id, sport_type, "fit", fit_path
                    )
                    if not downloaded:
                        raise Exception("Download failed - no file returned")

                self.queue_service.update_item_status(
                    item_id, ITEM_STATUS_DOWNLOADING, local_path=str(fit_path)
                )

                # Step 2: Upload to Garmin
                self.queue_service.update_item_status(item_id, ITEM_STATUS_UPLOADING)

                garmin_id = garmin_client.upload_fit(
                    fit_path,
                    activity_name,
                    start_time=item.get("activity_time"),
                )

                if garmin_id == "duplicate":
                    # Duplicate is a success (skipped)
                    self.queue_service.update_item_status(
                        item_id,
                        ITEM_STATUS_SKIPPED,
                        garmin_id="duplicate",
                        local_path=str(fit_path),
                        metadata_status=METADATA_STATUS_SKIPPED,
                    )
                    logger.info(f"Item {item_id} skipped (duplicate)")
                    return

                if not garmin_id:
                    raise Exception("Upload failed - no Garmin ID returned")

                # Step 3: Apply metadata (warning-only)
                metadata_status, metadata_error = self._apply_metadata(
                    garmin_client, garmin_id, item, settings
                )

                self.queue_service.update_item_status(
                    item_id,
                    ITEM_STATUS_SUCCESS,
                    garmin_id=garmin_id,
                    local_path=str(fit_path),
                    metadata_status=metadata_status,
                    metadata_error=metadata_error,
                )
                logger.info(f"Item {item_id} completed: Garmin ID {garmin_id}")

                if self._on_item_complete:
                    updated_item = self.queue_service.get_job_items(
                        item["job_id"], limit=1
                    )
                    if updated_item:
                        self._on_item_complete(item_id, updated_item[0])

                return

            except Exception as e:
                last_error = str(e)
                attempt += 1
                self.queue_service.increment_item_retry(item_id)

                if attempt < max_attempts:
                    # Exponential backoff with jitter
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    delay = delay * (0.5 + random.random())  # Add jitter
                    logger.warning(
                        f"Item {item_id} failed (attempt {attempt}/{max_attempts}): {e}. "
                        f"Retrying in {delay:.1f}s"
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"Item {item_id} failed after {max_attempts} attempts: {e}")

        # All retries exhausted
        self.queue_service.update_item_status(
            item_id,
            ITEM_STATUS_FAILED,
            error_message=last_error,
        )

    def _apply_metadata(
        self,
        garmin_client: GarminClient,
        garmin_id: str,
        item: dict[str, Any],
        settings: dict[str, Any],
    ) -> tuple[str, Optional[str]]:
        """
        Apply metadata to uploaded activity (title, description, privacy, gear).

        Returns:
            Tuple of (metadata_status, metadata_error)
        """
        naming = settings.get("naming", {})
        privacy = settings.get("privacy", {})
        gear = settings.get("gear", {})

        # Build template context
        context = self._build_metadata_context(item)

        errors = []

        # Apply title
        title_template = naming.get("title_template", "")
        if title_template:
            try:
                renderer = TemplateRenderer(title_template)
                title = renderer.render(context)
                if title:
                    success = garmin_client._set_activity_name(garmin_id, title)
                    if not success:
                        errors.append("Failed to set activity name")
            except Exception as e:
                errors.append(f"Title error: {e}")

        # Apply description (if supported - may need API extension)
        # desc_template = naming.get("description_template", "")
        # TODO: Implement description update API if Garmin supports it

        # Apply privacy (if not default)
        visibility = privacy.get("visibility", "default")
        if visibility != "default":
            try:
                success = self._set_activity_privacy(garmin_client, garmin_id, visibility)
                if not success:
                    errors.append(f"Failed to set privacy to {visibility}")
            except Exception as e:
                errors.append(f"Privacy error: {e}")

        # Apply gear (if enabled)
        if gear.get("enabled") and gear.get("gear_id"):
            try:
                success = self._link_gear(garmin_client, garmin_id, gear["gear_id"])
                if not success:
                    errors.append("Failed to link gear")
            except Exception as e:
                errors.append(f"Gear error: {e}")

        if errors:
            return METADATA_STATUS_FAILED, "; ".join(errors)
        return METADATA_STATUS_SUCCESS, None

    def _build_metadata_context(self, item: dict[str, Any]) -> dict[str, Any]:
        """Build template context from item data."""
        from datetime import datetime

        sport_type = item.get("sport_type", 9999)
        sport = COROS_SPORT_NAMES.get(sport_type, "运动")

        raw_start_time = item.get("activity_time")
        start_time = None
        start_local = None
        if raw_start_time is not None and raw_start_time != "":
            # COROS startTime can be epoch seconds (or ms) or a formatted string.
            try:
                if isinstance(raw_start_time, (int, float)):
                    ts = float(raw_start_time)
                elif isinstance(raw_start_time, str) and raw_start_time.strip().isdigit():
                    ts = float(raw_start_time.strip())
                else:
                    ts = None

                if ts is not None:
                    if ts > 10_000_000_000:
                        ts = ts / 1000.0
                    start_time = datetime.fromtimestamp(ts)
                    start_local = start_time
                else:
                    start_time_str = str(raw_start_time)
                    try:
                        start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
                        start_local = start_time
                    except ValueError:
                        start_time = datetime.fromisoformat(
                            start_time_str.replace("Z", "+00:00")
                        )
                        start_local = start_time
            except Exception:
                pass

        return {
            "label_id": item.get("label_id", ""),
            "sport": sport,
            "sport_type": sport_type,
            "start_time": start_time,
            "start_local": start_local,
            "duration_seconds": 0,
            "duration_formatted": "0:00",
            "distance_km": 0,
            "distance_m": 0,
            "name": item.get("activity_name", ""),
            "calories": 0,
        }

    def _set_activity_privacy(
        self, garmin_client: GarminClient, activity_id: str, visibility: str
    ) -> bool:
        """Set activity privacy level."""
        try:
            import garth

            # Map visibility to Garmin privacy type
            privacy_map = {
                "private": "private",
                "public": "public",
            }
            privacy_type = privacy_map.get(visibility)
            if not privacy_type:
                return True  # 'default' means no change

            path = f"/activity-service/activity/{activity_id}"
            data = {"activityId": activity_id, "privacy": {"typeKey": privacy_type}}
            garth.client.connectapi(path, method="PUT", json=data)
            return True
        except Exception as e:
            logger.warning(f"Failed to set privacy for {activity_id}: {e}")
            return False

    def _link_gear(
        self, garmin_client: GarminClient, activity_id: str, gear_id: str
    ) -> bool:
        """Link gear to activity."""
        try:
            import garth

            path = f"/gear-service/gear/link/{gear_id}/activity/{activity_id}"
            garth.client.connectapi(path, method="PUT")
            return True
        except Exception as e:
            logger.warning(f"Failed to link gear {gear_id} to activity {activity_id}: {e}")
            return False


# Global worker instance (singleton for web app)
_worker_instance: Optional[TransferWorker] = None
_worker_lock = threading.Lock()


def get_worker() -> TransferWorker:
    """Get the global worker instance."""
    global _worker_instance
    with _worker_lock:
        if _worker_instance is None:
            _worker_instance = TransferWorker()
        return _worker_instance


def reset_worker() -> None:
    """Reset the global worker instance (for testing)."""
    global _worker_instance
    with _worker_lock:
        if _worker_instance is not None:
            _worker_instance.stop(wait=True)
            _worker_instance = None
