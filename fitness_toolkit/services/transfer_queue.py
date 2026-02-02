"""Transfer queue service - async job management for COROS->Garmin sync."""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from fitness_toolkit.database import get_connection
from fitness_toolkit.services.transfer_settings import TransferSettingsService

logger = logging.getLogger(__name__)

# Job status values
JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_PAUSED = "paused"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_CANCELLED = "cancelled"

# Item status values
ITEM_STATUS_PENDING = "pending"
ITEM_STATUS_DOWNLOADING = "downloading"
ITEM_STATUS_UPLOADING = "uploading"
ITEM_STATUS_SUCCESS = "success"
ITEM_STATUS_SKIPPED = "skipped"
ITEM_STATUS_FAILED = "failed"

# Metadata status values
METADATA_STATUS_PENDING = "pending"
METADATA_STATUS_SUCCESS = "success"
METADATA_STATUS_FAILED = "failed"
METADATA_STATUS_SKIPPED = "skipped"


class TransferQueueService:
    """Service for managing async transfer jobs and items."""

    def __init__(self):
        self.settings_service = TransferSettingsService()

    def create_job(
        self,
        start_date: str,
        end_date: str,
        activities: list[dict[str, Any]],
        sport_types: Optional[list[str]] = None,
    ) -> int:
        """
        Create a new transfer job with items.

        Args:
            start_date: Start date string (YYYY-MM-DD)
            end_date: End date string (YYYY-MM-DD)
            activities: List of COROS activity dicts (must have labelId, sportType)
            sport_types: Optional list of sport types to filter

        Returns:
            Job ID
        """
        # Snapshot current settings
        settings = self.settings_service.get_settings()
        settings_snapshot = json.dumps(settings, ensure_ascii=False)

        sport_types_json = json.dumps(sport_types) if sport_types else None

        with get_connection() as conn:
            cursor = conn.cursor()

            # Create job
            cursor.execute(
                """INSERT INTO transfer_jobs 
                   (status, start_date, end_date, sport_types, settings_snapshot, total_items)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    JOB_STATUS_PENDING,
                    start_date,
                    end_date,
                    sport_types_json,
                    settings_snapshot,
                    len(activities),
                ),
            )
            job_id = cursor.lastrowid
            if job_id is None:
                raise RuntimeError("Failed to create job: no lastrowid returned")

            # Create items
            for activity in activities:
                cursor.execute(
                    """INSERT INTO transfer_items
                       (job_id, label_id, sport_type, activity_name, activity_time, status)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        job_id,
                        activity.get("labelId", ""),
                        activity.get("sportType"),
                        activity.get("name", ""),
                        activity.get("startTime", ""),
                        ITEM_STATUS_PENDING,
                    ),
                )

            conn.commit()
            logger.info(f"Created transfer job {job_id} with {len(activities)} items")
            return job_id

    def get_job(self, job_id: int) -> Optional[dict[str, Any]]:
        """
        Get a job by ID with summary stats.

        Returns:
            Job dict with fields or None if not found
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM transfer_jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                return None

            job = dict(row)

            # Parse JSON fields
            if job.get("sport_types"):
                job["sport_types"] = json.loads(job["sport_types"])
            if job.get("settings_snapshot"):
                job["settings_snapshot"] = json.loads(job["settings_snapshot"])

            return job

    def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        List recent jobs (newest first).

        Args:
            limit: Max number of jobs to return

        Returns:
            List of job dicts
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, status, start_date, end_date, sport_types,
                          total_items, completed_items, success_count, skipped_count, 
                          failed_count, error_message, created_at, started_at, completed_at
                   FROM transfer_jobs
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,),
            )
            jobs = []
            for row in cursor.fetchall():
                job = dict(row)
                if job.get("sport_types"):
                    job["sport_types"] = json.loads(job["sport_types"])
                jobs.append(job)
            return jobs

    def get_job_items(
        self,
        job_id: int,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get items for a job, optionally filtered by status.

        Args:
            job_id: Job ID
            status: Optional status filter
            limit: Max number of items to return

        Returns:
            List of item dicts
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    """SELECT * FROM transfer_items
                       WHERE job_id = ? AND status = ?
                       ORDER BY id
                       LIMIT ?""",
                    (job_id, status, limit),
                )
            else:
                cursor.execute(
                    """SELECT * FROM transfer_items
                       WHERE job_id = ?
                       ORDER BY id
                       LIMIT ?""",
                    (job_id, limit),
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_items(self, job_id: int, limit: int = 10) -> list[dict[str, Any]]:
        """
        Get pending items for a job (for worker to process).

        Args:
            job_id: Job ID
            limit: Max number of items to return

        Returns:
            List of pending item dicts
        """
        return self.get_job_items(job_id, status=ITEM_STATUS_PENDING, limit=limit)

    def update_job_status(
        self,
        job_id: int,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Update job status.

        Args:
            job_id: Job ID
            status: New status
            error_message: Optional error message (for failed status)

        Returns:
            True if job was updated
        """
        with get_connection() as conn:
            cursor = conn.cursor()

            # Set timestamps based on status
            now = datetime.now().isoformat()
            if status == JOB_STATUS_RUNNING:
                cursor.execute(
                    """UPDATE transfer_jobs
                       SET status = ?, started_at = ?
                       WHERE id = ?""",
                    (status, now, job_id),
                )
            elif status in (JOB_STATUS_COMPLETED, JOB_STATUS_FAILED, JOB_STATUS_CANCELLED):
                cursor.execute(
                    """UPDATE transfer_jobs
                       SET status = ?, error_message = ?, completed_at = ?
                       WHERE id = ?""",
                    (status, error_message, now, job_id),
                )
            else:
                cursor.execute(
                    """UPDATE transfer_jobs
                       SET status = ?, error_message = ?
                       WHERE id = ?""",
                    (status, error_message, job_id),
                )

            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info(f"Updated job {job_id} status to {status}")
            return updated

    def update_item_status(
        self,
        item_id: int,
        status: str,
        error_message: Optional[str] = None,
        garmin_id: Optional[str] = None,
        local_path: Optional[str] = None,
        metadata_status: Optional[str] = None,
        metadata_error: Optional[str] = None,
    ) -> bool:
        """
        Update item status and optionally other fields.

        Args:
            item_id: Item ID
            status: New status
            error_message: Optional error message
            garmin_id: Optional Garmin activity ID
            local_path: Optional local file path
            metadata_status: Optional metadata status
            metadata_error: Optional metadata error

        Returns:
            True if item was updated
        """
        with get_connection() as conn:
            cursor = conn.cursor()

            # Build dynamic update
            fields = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
            values: list[Any] = [status]

            if error_message is not None:
                fields.append("error_message = ?")
                values.append(error_message)

            if garmin_id is not None:
                fields.append("garmin_id = ?")
                values.append(garmin_id)

            if local_path is not None:
                fields.append("local_path = ?")
                values.append(local_path)

            if metadata_status is not None:
                fields.append("metadata_status = ?")
                values.append(metadata_status)

            if metadata_error is not None:
                fields.append("metadata_error = ?")
                values.append(metadata_error)

            values.append(item_id)
            sql = f"UPDATE transfer_items SET {', '.join(fields)} WHERE id = ?"

            cursor.execute(sql, values)
            conn.commit()

            updated = cursor.rowcount > 0
            if updated:
                logger.debug(f"Updated item {item_id} status to {status}")

            return updated

    def increment_item_retry(self, item_id: int) -> int:
        """
        Increment retry count for an item.

        Args:
            item_id: Item ID

        Returns:
            New retry count
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE transfer_items
                   SET retry_count = retry_count + 1, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (item_id,),
            )
            conn.commit()

            cursor.execute("SELECT retry_count FROM transfer_items WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            return row["retry_count"] if row else 0

    def update_job_counts(self, job_id: int) -> dict[str, int]:
        """
        Recalculate and update job counts based on item statuses.

        Args:
            job_id: Job ID

        Returns:
            Dict with count fields
        """
        with get_connection() as conn:
            cursor = conn.cursor()

            # Count items by status
            cursor.execute(
                """SELECT 
                       COUNT(*) as total,
                       SUM(CASE WHEN status IN (?, ?, ?) THEN 1 ELSE 0 END) as completed,
                       SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as success,
                       SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as skipped,
                       SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as failed
                   FROM transfer_items
                   WHERE job_id = ?""",
                (
                    ITEM_STATUS_SUCCESS,
                    ITEM_STATUS_SKIPPED,
                    ITEM_STATUS_FAILED,
                    ITEM_STATUS_SUCCESS,
                    ITEM_STATUS_SKIPPED,
                    ITEM_STATUS_FAILED,
                    job_id,
                ),
            )
            row = cursor.fetchone()
            counts = {
                "total_items": row["total"] or 0,
                "completed_items": row["completed"] or 0,
                "success_count": row["success"] or 0,
                "skipped_count": row["skipped"] or 0,
                "failed_count": row["failed"] or 0,
            }

            # Update job
            cursor.execute(
                """UPDATE transfer_jobs
                   SET total_items = ?, completed_items = ?, 
                       success_count = ?, skipped_count = ?, failed_count = ?
                   WHERE id = ?""",
                (
                    counts["total_items"],
                    counts["completed_items"],
                    counts["success_count"],
                    counts["skipped_count"],
                    counts["failed_count"],
                    job_id,
                ),
            )
            conn.commit()

            return counts

    def cancel_job(self, job_id: int) -> bool:
        """
        Cancel a job and all its pending items.

        Args:
            job_id: Job ID

        Returns:
            True if job was cancelled
        """
        with get_connection() as conn:
            cursor = conn.cursor()

            # Check if job can be cancelled
            cursor.execute("SELECT status FROM transfer_jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                return False

            if row["status"] in (JOB_STATUS_COMPLETED, JOB_STATUS_CANCELLED):
                logger.warning(f"Job {job_id} cannot be cancelled (status: {row['status']})")
                return False

            # Cancel pending items
            cursor.execute(
                """UPDATE transfer_items
                   SET status = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE job_id = ? AND status = ?""",
                (ITEM_STATUS_FAILED, job_id, ITEM_STATUS_PENDING),
            )

            # Update job status
            now = datetime.now().isoformat()
            cursor.execute(
                """UPDATE transfer_jobs
                   SET status = ?, completed_at = ?
                   WHERE id = ?""",
                (JOB_STATUS_CANCELLED, now, job_id),
            )

            conn.commit()
            logger.info(f"Cancelled job {job_id}")

            # Update counts
            self.update_job_counts(job_id)
            return True

    def delete_job(self, job_id: int) -> bool:
        """
        Delete a job and all its items.

        Args:
            job_id: Job ID

        Returns:
            True if job was deleted
        """
        with get_connection() as conn:
            cursor = conn.cursor()

            # Delete items first (FK cascade should handle this but be explicit)
            cursor.execute("DELETE FROM transfer_items WHERE job_id = ?", (job_id,))

            # Delete job
            cursor.execute("DELETE FROM transfer_jobs WHERE id = ?", (job_id,))
            conn.commit()

            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted job {job_id}")
            return deleted
