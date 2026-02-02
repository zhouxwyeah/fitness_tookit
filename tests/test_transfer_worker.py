"""Tests for transfer worker service and worker control APIs."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fitness_toolkit.database import init_db, save_account
from fitness_toolkit.crypto import encrypt_password
from fitness_toolkit.services.transfer_queue import (
    TransferQueueService,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_PAUSED,
    ITEM_STATUS_PENDING,
    ITEM_STATUS_SUCCESS,
    ITEM_STATUS_FAILED,
    METADATA_STATUS_SUCCESS,
)
from fitness_toolkit.services.transfer_worker import (
    TransferWorker,
    get_worker,
    reset_worker,
)
from fitness_toolkit.web.app import create_app


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Set up temp database."""
    db_file = tmp_path / "test_fitness.db"
    monkeypatch.setattr("fitness_toolkit.config.Config.DATABASE_PATH", db_file)
    monkeypatch.setattr("fitness_toolkit.database.Config.DATABASE_PATH", db_file)
    
    # Also patch downloads dir
    downloads_dir = tmp_path / "downloads"
    downloads_dir.mkdir()
    monkeypatch.setattr("fitness_toolkit.config.Config.DOWNLOADS_DIR", downloads_dir)
    
    init_db()
    return db_file


@pytest.fixture
def setup_accounts(db_path):
    """Set up test accounts in database."""
    # Save encrypted accounts
    save_account("coros", "test@coros.com", encrypt_password("testpass"))
    save_account("garmin", "test@garmin.com", encrypt_password("testpass"))


@pytest.fixture
def queue_service(db_path):
    """Create TransferQueueService with temp database."""
    return TransferQueueService()


@pytest.fixture
def client(db_path):
    """Create test client with isolated database."""
    reset_worker()  # Reset global worker for each test
    app = create_app(testing=True)
    with app.test_client() as test_client:
        yield test_client
    reset_worker()  # Cleanup


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
    ]


class TestTransferWorker:
    """Tests for TransferWorker class."""

    def test_worker_initial_state(self, db_path):
        """Test worker initial state."""
        worker = TransferWorker()
        assert not worker.is_running
        assert not worker.is_paused
        assert worker.current_job_id is None

    def test_worker_start_stop(self, db_path):
        """Test starting and stopping worker."""
        worker = TransferWorker()
        
        assert worker.start()
        assert worker.is_running
        
        assert worker.stop(wait=True, timeout=5.0)
        assert not worker.is_running

    def test_worker_double_start(self, db_path):
        """Test that starting an already running worker returns False."""
        worker = TransferWorker()
        
        worker.start()
        assert not worker.start()  # Second start should fail
        
        worker.stop()

    def test_worker_pause_resume(self, db_path):
        """Test pausing and resuming worker."""
        worker = TransferWorker()
        
        worker.start()
        
        assert worker.pause()
        assert worker.is_paused
        
        assert worker.resume()
        assert not worker.is_paused
        
        worker.stop()

    def test_worker_pause_not_running(self, db_path):
        """Test that pausing a non-running worker returns False."""
        worker = TransferWorker()
        assert not worker.pause()

    def test_process_job_not_found(self, db_path, queue_service):
        """Test processing non-existent job."""
        worker = TransferWorker(queue_service=queue_service)
        
        assert not worker.process_job(99999)


class TestWorkerJobProcessing:
    """Tests for worker job processing (mocked)."""

    def test_worker_processes_job(self, db_path, setup_accounts, queue_service, sample_activities, monkeypatch, tmp_path):
        """Test that worker processes a job successfully."""
        # Create a job
        job_id = queue_service.create_job(
            "2024-01-15",
            "2024-01-15",
            sample_activities,
        )

        # Mock the client creation
        mock_coros = MagicMock()
        mock_coros.download_activity.return_value = tmp_path / "test.fit"
        
        mock_garmin = MagicMock()
        mock_garmin.upload_fit.return_value = "garmin-123"
        mock_garmin._set_activity_name.return_value = True

        # Make sure upload_fit accepts the new start_time kwarg
        def _upload_fit(file_path, activity_name=None, start_time=None):
            return "garmin-123"

        mock_garmin.upload_fit.side_effect = _upload_fit

        # Create test file
        (tmp_path / "test.fit").write_bytes(b"fake fit data")

        worker = TransferWorker(queue_service=queue_service)

        with patch.object(worker, '_create_coros_client', return_value=mock_coros):
            with patch.object(worker, '_create_garmin_client', return_value=mock_garmin):
                # Start processing
                worker.process_job(job_id)
                
                # Wait a bit for processing
                time.sleep(0.5)
                worker.stop(wait=True, timeout=5.0)

        # Check job status
        job = queue_service.get_job(job_id)
        # Job should be completed or still running depending on timing
        assert job["status"] in (JOB_STATUS_RUNNING, JOB_STATUS_COMPLETED)


class TestWorkerControlAPIs:
    """Tests for worker control web APIs."""

    def test_get_worker_status(self, client):
        """Test getting worker status."""
        response = client.get("/api/transfer/worker/status")
        assert response.status_code == 200
        
        data = response.get_json()
        assert "running" in data
        assert "paused" in data
        assert "current_job_id" in data

    def test_pause_worker_not_running(self, client):
        """Test pausing worker when not running."""
        response = client.post("/api/transfer/worker/pause")
        assert response.status_code == 400

    def test_resume_worker_not_running(self, client):
        """Test resuming worker when not running."""
        response = client.post("/api/transfer/worker/resume")
        assert response.status_code == 400

    def test_stop_worker(self, client):
        """Test stopping worker."""
        response = client.post("/api/transfer/worker/stop")
        assert response.status_code == 200
        
        data = response.get_json()
        assert data["running"] is False

    def test_start_job_not_found(self, client):
        """Test starting non-existent job."""
        response = client.post("/api/transfer/jobs/99999/start")
        assert response.status_code == 404


class TestRerunMetadataAPI:
    """Tests for rerun-metadata API."""

    def test_rerun_metadata_job_not_found(self, client):
        """Test rerun metadata for non-existent job."""
        response = client.post("/api/transfer/jobs/99999/rerun-metadata")
        assert response.status_code == 404

    def test_rerun_metadata_no_failed_items(self, client, db_path, monkeypatch, sample_activities):
        """Test rerun metadata when no items have failed metadata."""
        # Create mock clients
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

        # Try rerun metadata
        response = client.post(f"/api/transfer/jobs/{job_id}/rerun-metadata")
        assert response.status_code == 200
        
        data = response.get_json()
        assert data["rerun_count"] == 0


class TestGarminClientRefactored:
    """Tests for refactored GarminClient."""


def test_metadata_context_parses_epoch_start_time(db_path):
    """Ensure worker context can parse COROS epoch startTime."""
    worker = TransferWorker()
    ctx = worker._build_metadata_context(
        {
            "label_id": "x",
            "sport_type": 100,
            "activity_name": "Run",
            "activity_time": 1705307400,  # epoch seconds
        }
    )

    assert ctx["start_local"] is not None

    def test_garmin_client_has_instance_client(self):
        """Test that GarminClient uses per-instance client."""
        from fitness_toolkit.clients.garmin import GarminClient
        
        client1 = GarminClient()
        client2 = GarminClient()
        
        # Each instance should have its own _client attribute (initially None)
        assert client1._client is None
        assert client2._client is None
        
        # Accessing client property should create instance
        # (We don't actually test this as it would try to connect)
