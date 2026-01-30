"""Tests for web transfer functionality."""

from unittest.mock import MagicMock

import pytest

from fitness_toolkit.web.app import create_app


@pytest.fixture
def client(monkeypatch):
    """Create test client with mocked scheduler."""
    # Mock scheduler to avoid background thread issues in tests
    mock_scheduler = MagicMock()
    monkeypatch.setattr(
        "fitness_toolkit.web.app.SchedulerService", lambda: mock_scheduler
    )

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_transfer_page_loads(client):
    """Test transfer page loads successfully."""
    response = client.get("/")
    assert response.status_code == 200
    assert "同步到佳明".encode() in response.data


def test_transfer_api_success(client, monkeypatch):
    """Test transfer API returns expected structure."""
    mock_result = {
        "total": 3,
        "downloaded": 3,
        "uploaded": 2,
        "skipped": 1,
        "failed": [],
        "activities": [
            {
                "label_id": "123",
                "name": "Morning Run",
                "time": "2024-01-15",
                "status": "success",
                "garmin_id": "456",
            }
        ],
    }

    mock_transfer_service = MagicMock()
    mock_transfer_service.transfer.return_value = mock_result
    monkeypatch.setattr(
        "fitness_toolkit.web.app.TransferService", lambda: mock_transfer_service
    )

    response = client.post(
        "/api/transfer",
        json={
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "sport_types": ["running"],
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 3
    assert data["uploaded"] == 2
    assert data["skipped"] == 1
    assert len(data["activities"]) == 1


def test_transfer_api_missing_dates(client):
    """Test transfer API requires dates."""
    response = client.post("/api/transfer", json={"start_date": "2024-01-01"})

    assert response.status_code == 400
    data = response.get_json()
    assert "end_date" in data["error"].lower()


def test_transfer_api_invalid_date_format(client):
    """Test transfer API validates date format."""
    response = client.post(
        "/api/transfer", json={"start_date": "01-01-2024", "end_date": "2024-01-31"}
    )

    assert response.status_code == 400
    data = response.get_json()
    assert "date format" in data["error"].lower()


def test_transfer_api_invalid_date_range(client):
    """Test transfer API validates date range."""
    response = client.post(
        "/api/transfer", json={"start_date": "2024-02-01", "end_date": "2024-01-01"}
    )

    assert response.status_code == 400
    data = response.get_json()
    assert "start_date" in data["error"].lower()


def test_transfer_api_invalid_sport_types_type(client):
    """Test transfer API validates sport_types is a list."""
    response = client.post(
        "/api/transfer",
        json={
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "sport_types": "running",
        },
    )

    assert response.status_code == 400
    data = response.get_json()
    assert "list" in data["error"].lower()


def test_transfer_api_value_error(client, monkeypatch):
    """Test transfer API handles ValueError (missing accounts)."""
    mock_transfer_service = MagicMock()
    mock_transfer_service.transfer.side_effect = ValueError("COROS not configured")
    monkeypatch.setattr(
        "fitness_toolkit.web.app.TransferService", lambda: mock_transfer_service
    )

    response = client.post(
        "/api/transfer", json={"start_date": "2024-01-01", "end_date": "2024-01-31"}
    )

    assert response.status_code == 400
    data = response.get_json()
    assert "coros" in data["error"].lower()


def test_transfer_api_exception(client, monkeypatch):
    """Test transfer API handles unexpected exceptions."""
    mock_transfer_service = MagicMock()
    mock_transfer_service.transfer.side_effect = Exception("Network error")
    monkeypatch.setattr(
        "fitness_toolkit.web.app.TransferService", lambda: mock_transfer_service
    )

    response = client.post(
        "/api/transfer", json={"start_date": "2024-01-01", "end_date": "2024-01-31"}
    )

    assert response.status_code == 500
    data = response.get_json()
    assert "network error" in data["error"].lower()


def test_transfer_history_api(client):
    """Test transfer history API."""
    response = client.get("/api/history/transfer?limit=10")

    assert response.status_code == 200
    data = response.get_json()
    assert "history" in data
    assert isinstance(data["history"], list)


def test_transfer_history_api_invalid_type(client):
    """Test transfer history API rejects invalid operation type."""
    response = client.get("/api/history/invalid")

    assert response.status_code == 400
    data = response.get_json()
    assert "invalid" in data["error"].lower()
