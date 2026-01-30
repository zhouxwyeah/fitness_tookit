"""Tests for web scheduler functionality."""

import pytest

from fitness_toolkit.web.app import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_scheduler_page_loads(client):
    """Test scheduler page loads successfully."""
    response = client.get("/")
    assert response.status_code == 200
    assert "定时任务".encode() in response.data


def test_list_tasks_api(client):
    """Test list tasks API."""
    response = client.get("/api/tasks")
    assert response.status_code == 200
    data = response.get_json()
    assert "tasks" in data
    assert isinstance(data["tasks"], list)
