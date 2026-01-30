"""Tests for web download functionality."""

import pytest

from fitness_toolkit.web.app import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_download_page_loads(client):
    """Test download page loads successfully."""
    response = client.get("/")
    assert response.status_code == 200
    assert "下载数据".encode() in response.data


def test_download_api_requires_account(client):
    """Test download API requires valid account."""
    response = client.post(
        "/api/downloads",
        json={
            "account_id": "unknown_platform",
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "format": "tcx",
        },
    )
    # Should fail because account is not configured
    assert response.status_code == 400
