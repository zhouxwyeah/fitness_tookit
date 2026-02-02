"""Tests for transfer queue service and job APIs."""

import json
from unittest.mock import MagicMock, patch

import pytest

from fitness_toolkit.database import init_db
from fitness_toolkit.services.transfer_queue import (
    TransferQueueService,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_CANCELLED,
    JOB_STATUS_FAILED,
    ITEM_STATUS_PENDING,
    ITEM_STATUS_SUCCESS,
    ITEM_STATUS_SKIPPED,
    ITEM_STATUS_FAILED,
)
from fitness_toolkit.web.app import create_app


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Set up temp database."""
    db_file = tmp_path / "test_fitness.db"
    monkeypatch.setattr("fitness_toolkit.config.Config.DATABASE_PATH", db_file)
    monkeypatch.setattr("fitness_toolkit.database.Config.DATABASE_PATH", db_file)
    init_db()
    return db_file


@pytest.fixture
def queue_service(db_path):
    """Create TransferQueueService with temp database."""
    return TransferQueueService()


@pytest.fixture
def client(db_path):
    """Create test client with isolated database."""
    app = create_app(testing=True)
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def sample_activities():
    """Sample COROS activities for testing."""
    return [
        {
            "labelId": "activity-001",
            "sportType": 100,
            "name": "Morning Run",
            "startTime": "2024-01-15 08:30:00",
        },
        {
            "labelId": "activity-002",
            "sportType": 200,
            "name": "Bike Ride",
            "startTime": "2024-01-15 14:00:00",
        },
        {
            "labelId": "activity-003",
            "sportType": 100,
            "name": "Evening Run",
            "startTime": "2024-01-15 18:30:00",
        },
    ]


class TestTransferQueueService:
    """Tests for TransferQueueService."""

    def test_create_job(self, queue_service, sample_activities):
        """Test creating a job with items."""
        job_id = queue_service.create_job(
            start_date="2024-01-15",
            end_date="2024-01-15",
            activities=sample_activities,
            sport_types=None,
        )

        assert job_id is not None
        assert job_id > 0

        job = queue_service.get_job(job_id)
        assert job is not None
        assert job["status"] == JOB_STATUS_PENDING
        assert job["total_items"] == 3
        assert job["start_date"] == "2024-01-15"
        assert job["end_date"] == "2024-01-15"

    def test_create_job_with_sport_types(self, queue_service, sample_activities):
        """Test creating a job with sport type filter."""
        job_id = queue_service.create_job(
            start_date="2024-01-15",
            end_date="2024-01-15",
            activities=sample_activities,
            sport_types=["100", "200"],
        )

        job = queue_service.get_job(job_id)
        assert job["sport_types"] == ["100", "200"]

    def test_create_job_snapshots_settings(self, queue_service, sample_activities):
        """Test that job snapshots current settings."""
        job_id = queue_service.create_job(
            start_date="2024-01-15",
            end_date="2024-01-15",
            activities=sample_activities,
        )

        job = queue_service.get_job(job_id)
        assert "settings_snapshot" in job
        assert isinstance(job["settings_snapshot"], dict)
        assert "concurrency" in job["settings_snapshot"]

    def test_get_job_not_found(self, queue_service):
        """Test getting non-existent job."""
        job = queue_service.get_job(99999)
        assert job is None

    def test_list_jobs(self, queue_service, sample_activities):
        """Test listing jobs."""
        # Create multiple jobs
        job_id1 = queue_service.create_job("2024-01-15", "2024-01-15", sample_activities)
        job_id2 = queue_service.create_job("2024-01-16", "2024-01-16", sample_activities[:1])

        jobs = queue_service.list_jobs(limit=10)
        assert len(jobs) == 2
        # Both jobs should be in the list
        job_ids = [j["id"] for j in jobs]
        assert job_id1 in job_ids
        assert job_id2 in job_ids

    def test_list_jobs_limit(self, queue_service, sample_activities):
        """Test list jobs respects limit."""
        for i in range(5):
            queue_service.create_job(f"2024-01-{15+i:02d}", f"2024-01-{15+i:02d}", sample_activities[:1])

        jobs = queue_service.list_jobs(limit=3)
        assert len(jobs) == 3

    def test_get_job_items(self, queue_service, sample_activities):
        """Test getting items for a job."""
        job_id = queue_service.create_job("2024-01-15", "2024-01-15", sample_activities)

        items = queue_service.get_job_items(job_id)
        assert len(items) == 3
        assert items[0]["label_id"] == "activity-001"
        assert items[0]["sport_type"] == 100
        assert items[0]["activity_name"] == "Morning Run"
        assert items[0]["status"] == ITEM_STATUS_PENDING

    def test_get_job_items_filter_by_status(self, queue_service, sample_activities):
        """Test filtering items by status."""
        job_id = queue_service.create_job("2024-01-15", "2024-01-15", sample_activities)
        items = queue_service.get_job_items(job_id)

        # Update one item status
        queue_service.update_item_status(items[0]["id"], ITEM_STATUS_SUCCESS)

        pending_items = queue_service.get_job_items(job_id, status=ITEM_STATUS_PENDING)
        assert len(pending_items) == 2

        success_items = queue_service.get_job_items(job_id, status=ITEM_STATUS_SUCCESS)
        assert len(success_items) == 1

    def test_update_job_status(self, queue_service, sample_activities):
        """Test updating job status."""
        job_id = queue_service.create_job("2024-01-15", "2024-01-15", sample_activities)

        # Update to running
        result = queue_service.update_job_status(job_id, JOB_STATUS_RUNNING)
        assert result is True

        job = queue_service.get_job(job_id)
        assert job["status"] == JOB_STATUS_RUNNING
        assert job["started_at"] is not None

    def test_update_job_status_completed(self, queue_service, sample_activities):
        """Test updating job status to completed."""
        job_id = queue_service.create_job("2024-01-15", "2024-01-15", sample_activities)

        queue_service.update_job_status(job_id, JOB_STATUS_COMPLETED)

        job = queue_service.get_job(job_id)
        assert job["status"] == JOB_STATUS_COMPLETED
        assert job["completed_at"] is not None

    def test_update_job_status_failed_with_error(self, queue_service, sample_activities):
        """Test updating job status to failed with error message."""
        job_id = queue_service.create_job("2024-01-15", "2024-01-15", sample_activities)

        queue_service.update_job_status(job_id, JOB_STATUS_FAILED, error_message="Connection timeout")

        job = queue_service.get_job(job_id)
        assert job["status"] == JOB_STATUS_FAILED
        assert job["error_message"] == "Connection timeout"

    def test_update_item_status(self, queue_service, sample_activities):
        """Test updating item status."""
        job_id = queue_service.create_job("2024-01-15", "2024-01-15", sample_activities)
        items = queue_service.get_job_items(job_id)

        result = queue_service.update_item_status(
            items[0]["id"],
            ITEM_STATUS_SUCCESS,
            garmin_id="garmin-12345",
            local_path="/path/to/file.fit",
        )
        assert result is True

        updated_items = queue_service.get_job_items(job_id)
        item = next(i for i in updated_items if i["id"] == items[0]["id"])
        assert item["status"] == ITEM_STATUS_SUCCESS
        assert item["garmin_id"] == "garmin-12345"
        assert item["local_path"] == "/path/to/file.fit"

    def test_update_item_status_with_error(self, queue_service, sample_activities):
        """Test updating item status to failed with error."""
        job_id = queue_service.create_job("2024-01-15", "2024-01-15", sample_activities)
        items = queue_service.get_job_items(job_id)

        queue_service.update_item_status(
            items[0]["id"],
            ITEM_STATUS_FAILED,
            error_message="Download failed: 404",
        )

        updated_items = queue_service.get_job_items(job_id)
        item = next(i for i in updated_items if i["id"] == items[0]["id"])
        assert item["status"] == ITEM_STATUS_FAILED
        assert item["error_message"] == "Download failed: 404"

    def test_increment_item_retry(self, queue_service, sample_activities):
        """Test incrementing retry count."""
        job_id = queue_service.create_job("2024-01-15", "2024-01-15", sample_activities)
        items = queue_service.get_job_items(job_id)
        item_id = items[0]["id"]

        count1 = queue_service.increment_item_retry(item_id)
        assert count1 == 1

        count2 = queue_service.increment_item_retry(item_id)
        assert count2 == 2

    def test_update_job_counts(self, queue_service, sample_activities):
        """Test recalculating job counts."""
        job_id = queue_service.create_job("2024-01-15", "2024-01-15", sample_activities)
        items = queue_service.get_job_items(job_id)

        # Update item statuses
        queue_service.update_item_status(items[0]["id"], ITEM_STATUS_SUCCESS)
        queue_service.update_item_status(items[1]["id"], ITEM_STATUS_SKIPPED)
        queue_service.update_item_status(items[2]["id"], ITEM_STATUS_FAILED)

        counts = queue_service.update_job_counts(job_id)
        assert counts["total_items"] == 3
        assert counts["completed_items"] == 3
        assert counts["success_count"] == 1
        assert counts["skipped_count"] == 1
        assert counts["failed_count"] == 1

        job = queue_service.get_job(job_id)
        assert job["success_count"] == 1
        assert job["skipped_count"] == 1
        assert job["failed_count"] == 1

    def test_cancel_job(self, queue_service, sample_activities):
        """Test cancelling a job."""
        job_id = queue_service.create_job("2024-01-15", "2024-01-15", sample_activities)
        items = queue_service.get_job_items(job_id)

        # Complete one item
        queue_service.update_item_status(items[0]["id"], ITEM_STATUS_SUCCESS)

        # Cancel the job
        result = queue_service.cancel_job(job_id)
        assert result is True

        job = queue_service.get_job(job_id)
        assert job["status"] == JOB_STATUS_CANCELLED
        assert job["completed_at"] is not None

        # Check that pending items were marked as failed
        updated_items = queue_service.get_job_items(job_id, status=ITEM_STATUS_FAILED)
        assert len(updated_items) == 2

    def test_cancel_completed_job_fails(self, queue_service, sample_activities):
        """Test that cancelling a completed job fails."""
        job_id = queue_service.create_job("2024-01-15", "2024-01-15", sample_activities)
        queue_service.update_job_status(job_id, JOB_STATUS_COMPLETED)

        result = queue_service.cancel_job(job_id)
        assert result is False

    def test_delete_job(self, queue_service, sample_activities):
        """Test deleting a job."""
        job_id = queue_service.create_job("2024-01-15", "2024-01-15", sample_activities)

        result = queue_service.delete_job(job_id)
        assert result is True

        job = queue_service.get_job(job_id)
        assert job is None

        items = queue_service.get_job_items(job_id)
        assert len(items) == 0

    def test_delete_nonexistent_job(self, queue_service):
        """Test deleting non-existent job."""
        result = queue_service.delete_job(99999)
        assert result is False


class TestTransferJobAPIs:
    """Tests for transfer job web APIs."""

    def test_create_job_missing_dates(self, client):
        """Test create job without required dates."""
        response = client.post(
            "/api/transfer/jobs",
            json={"sport_types": ["100"]},  # Missing start_date and end_date
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "start_date" in data["error"] or "end_date" in data["error"]

    def test_create_job_invalid_date_format(self, client):
        """Test create job with invalid date format."""
        response = client.post(
            "/api/transfer/jobs",
            json={"start_date": "2024/01/15", "end_date": "2024-01-15"},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "Invalid date format" in data["error"]

    def test_create_job_start_after_end(self, client):
        """Test create job with start date after end date."""
        response = client.post(
            "/api/transfer/jobs",
            json={"start_date": "2024-01-20", "end_date": "2024-01-15"},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "before" in data["error"].lower()

    def test_create_job_no_coros_account(self, client, monkeypatch):
        """Test create job when COROS not configured."""
        mock_service = MagicMock()
        mock_service.get_client.return_value = None
        monkeypatch.setattr(
            "fitness_toolkit.services.account.AccountService.get_client",
            mock_service.get_client,
        )

        response = client.post(
            "/api/transfer/jobs",
            json={"start_date": "2024-01-15", "end_date": "2024-01-15"},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "COROS" in data["error"]

    def test_create_job_no_garmin_account(self, client, monkeypatch):
        """Test create job when Garmin not configured."""
        mock_coros = MagicMock()
        mock_service = MagicMock()
        mock_service.get_client.side_effect = lambda p: mock_coros if p == "coros" else None
        monkeypatch.setattr(
            "fitness_toolkit.services.account.AccountService.get_client",
            mock_service.get_client,
        )

        response = client.post(
            "/api/transfer/jobs",
            json={"start_date": "2024-01-15", "end_date": "2024-01-15"},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "Garmin" in data["error"]

    def test_create_job_no_activities(self, client, monkeypatch):
        """Test create job when no activities found."""
        mock_coros = MagicMock()
        mock_coros.get_activities.return_value = []
        mock_garmin = MagicMock()

        mock_service = MagicMock()
        mock_service.get_client.side_effect = lambda p: mock_coros if p == "coros" else mock_garmin
        monkeypatch.setattr(
            "fitness_toolkit.services.account.AccountService.get_client",
            mock_service.get_client,
        )

        response = client.post(
            "/api/transfer/jobs",
            json={"start_date": "2024-01-15", "end_date": "2024-01-15"},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["job_id"] is None
        assert data["total_items"] == 0

    def test_create_job_success(self, client, monkeypatch, sample_activities):
        """Test successful job creation."""
        mock_coros = MagicMock()
        mock_coros.get_activities.return_value = sample_activities
        mock_garmin = MagicMock()

        mock_service = MagicMock()
        mock_service.get_client.side_effect = lambda p: mock_coros if p == "coros" else mock_garmin
        monkeypatch.setattr(
            "fitness_toolkit.services.account.AccountService.get_client",
            mock_service.get_client,
        )

        response = client.post(
            "/api/transfer/jobs",
            json={"start_date": "2024-01-15", "end_date": "2024-01-15"},
            content_type="application/json",
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["job_id"] is not None
        assert data["total_items"] == 3

    def test_list_jobs_empty(self, client):
        """Test listing jobs when none exist."""
        response = client.get("/api/transfer/jobs")
        assert response.status_code == 200
        data = response.get_json()
        assert data["jobs"] == []

    def test_list_jobs(self, client, monkeypatch, sample_activities):
        """Test listing jobs."""
        mock_coros = MagicMock()
        mock_coros.get_activities.return_value = sample_activities
        mock_garmin = MagicMock()

        mock_service = MagicMock()
        mock_service.get_client.side_effect = lambda p: mock_coros if p == "coros" else mock_garmin
        monkeypatch.setattr(
            "fitness_toolkit.services.account.AccountService.get_client",
            mock_service.get_client,
        )

        # Create a job
        client.post(
            "/api/transfer/jobs",
            json={"start_date": "2024-01-15", "end_date": "2024-01-15"},
            content_type="application/json",
        )

        response = client.get("/api/transfer/jobs")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["jobs"]) == 1

    def test_list_jobs_with_limit(self, client, monkeypatch, sample_activities):
        """Test listing jobs with limit parameter."""
        mock_coros = MagicMock()
        mock_coros.get_activities.return_value = sample_activities[:1]
        mock_garmin = MagicMock()

        mock_service = MagicMock()
        mock_service.get_client.side_effect = lambda p: mock_coros if p == "coros" else mock_garmin
        monkeypatch.setattr(
            "fitness_toolkit.services.account.AccountService.get_client",
            mock_service.get_client,
        )

        # Create multiple jobs
        for i in range(5):
            client.post(
                "/api/transfer/jobs",
                json={"start_date": f"2024-01-{15+i:02d}", "end_date": f"2024-01-{15+i:02d}"},
                content_type="application/json",
            )

        response = client.get("/api/transfer/jobs?limit=3")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["jobs"]) == 3

    def test_get_job_not_found(self, client):
        """Test getting non-existent job."""
        response = client.get("/api/transfer/jobs/99999")
        assert response.status_code == 404

    def test_get_job_success(self, client, monkeypatch, sample_activities):
        """Test getting job details."""
        mock_coros = MagicMock()
        mock_coros.get_activities.return_value = sample_activities
        mock_garmin = MagicMock()

        mock_service = MagicMock()
        mock_service.get_client.side_effect = lambda p: mock_coros if p == "coros" else mock_garmin
        monkeypatch.setattr(
            "fitness_toolkit.services.account.AccountService.get_client",
            mock_service.get_client,
        )

        # Create a job
        create_response = client.post(
            "/api/transfer/jobs",
            json={"start_date": "2024-01-15", "end_date": "2024-01-15"},
            content_type="application/json",
        )
        job_id = create_response.get_json()["job_id"]

        response = client.get(f"/api/transfer/jobs/{job_id}")
        assert response.status_code == 200
        data = response.get_json()
        assert "job" in data
        assert "items" in data
        assert data["job"]["id"] == job_id
        assert len(data["items"]) == 3

    def test_delete_job_not_found(self, client):
        """Test deleting non-existent job."""
        response = client.delete("/api/transfer/jobs/99999")
        assert response.status_code == 404

    def test_delete_job_success(self, client, monkeypatch, sample_activities):
        """Test deleting a job."""
        mock_coros = MagicMock()
        mock_coros.get_activities.return_value = sample_activities
        mock_garmin = MagicMock()

        mock_service = MagicMock()
        mock_service.get_client.side_effect = lambda p: mock_coros if p == "coros" else mock_garmin
        monkeypatch.setattr(
            "fitness_toolkit.services.account.AccountService.get_client",
            mock_service.get_client,
        )

        # Create a job
        create_response = client.post(
            "/api/transfer/jobs",
            json={"start_date": "2024-01-15", "end_date": "2024-01-15"},
            content_type="application/json",
        )
        job_id = create_response.get_json()["job_id"]

        response = client.delete(f"/api/transfer/jobs/{job_id}")
        assert response.status_code == 200

        # Verify it's gone
        get_response = client.get(f"/api/transfer/jobs/{job_id}")
        assert get_response.status_code == 404

    def test_cancel_job_not_found(self, client):
        """Test cancelling non-existent job."""
        response = client.post("/api/transfer/jobs/99999/cancel")
        assert response.status_code == 400

    def test_cancel_job_success(self, client, monkeypatch, sample_activities):
        """Test cancelling a job."""
        mock_coros = MagicMock()
        mock_coros.get_activities.return_value = sample_activities
        mock_garmin = MagicMock()

        mock_service = MagicMock()
        mock_service.get_client.side_effect = lambda p: mock_coros if p == "coros" else mock_garmin
        monkeypatch.setattr(
            "fitness_toolkit.services.account.AccountService.get_client",
            mock_service.get_client,
        )

        # Create a job
        create_response = client.post(
            "/api/transfer/jobs",
            json={"start_date": "2024-01-15", "end_date": "2024-01-15"},
            content_type="application/json",
        )
        job_id = create_response.get_json()["job_id"]

        response = client.post(f"/api/transfer/jobs/{job_id}/cancel")
        assert response.status_code == 200
        data = response.get_json()
        assert data["job"]["status"] == JOB_STATUS_CANCELLED
