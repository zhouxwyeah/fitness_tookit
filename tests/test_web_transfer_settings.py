"""Tests for web transfer settings functionality."""

import json
from unittest.mock import MagicMock, patch

import pytest

from fitness_toolkit.web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create test client with isolated database."""
    # Use temp database
    db_path = tmp_path / "test_fitness.db"
    monkeypatch.setattr("fitness_toolkit.config.Config.DATABASE_PATH", db_path)
    monkeypatch.setattr("fitness_toolkit.database.Config.DATABASE_PATH", db_path)

    app = create_app(testing=True)
    with app.test_client() as test_client:
        yield test_client


class TestGetTransferSettings:
    """Tests for GET /api/settings/transfer."""

    def test_get_settings_returns_defaults(self, client):
        """Test that GET returns default settings when none exist."""
        response = client.get("/api/settings/transfer")
        assert response.status_code == 200

        data = response.get_json()
        assert "settings" in data
        assert "version" in data
        assert data["version"] == 1

        settings = data["settings"]
        assert settings["concurrency"] == 2
        assert settings["retry"]["max_attempts"] == 3
        assert settings["naming"]["title_template"] == "{sport} {start_local:%Y-%m-%d %H:%M}"
        assert settings["privacy"]["visibility"] == "default"
        assert settings["gear"]["enabled"] is False

    def test_get_settings_returns_saved_settings(self, client):
        """Test that GET returns previously saved settings."""
        # First, save custom settings
        custom_settings = {
            "settings": {
                "concurrency": 5,
                "naming": {"title_template": "Custom {sport}"},
            }
        }
        put_response = client.put(
            "/api/settings/transfer",
            json=custom_settings,
            content_type="application/json",
        )
        assert put_response.status_code == 200

        # Now get should return the saved settings
        response = client.get("/api/settings/transfer")
        assert response.status_code == 200

        data = response.get_json()
        assert data["settings"]["concurrency"] == 5
        assert data["settings"]["naming"]["title_template"] == "Custom {sport}"


class TestPutTransferSettings:
    """Tests for PUT /api/settings/transfer."""

    def test_put_settings_success(self, client):
        """Test successful settings update."""
        new_settings = {
            "settings": {
                "concurrency": 3,
                "retry": {
                    "max_attempts": 5,
                    "base_delay_seconds": 2,
                    "max_delay_seconds": 120,
                },
                "naming": {
                    "title_template": "{sport} - {distance_km}km",
                    "description_template": "Activity from COROS",
                },
                "privacy": {"visibility": "private"},
                "gear": {"enabled": True, "gear_id": "abc-123"},
            }
        }

        response = client.put(
            "/api/settings/transfer",
            json=new_settings,
            content_type="application/json",
        )
        assert response.status_code == 200

        data = response.get_json()
        assert data["settings"]["concurrency"] == 3
        assert data["settings"]["retry"]["max_attempts"] == 5
        assert data["settings"]["naming"]["title_template"] == "{sport} - {distance_km}km"
        assert data["settings"]["privacy"]["visibility"] == "private"
        assert data["settings"]["gear"]["enabled"] is True

    def test_put_settings_missing_body(self, client):
        """Test PUT without request body."""
        response = client.put("/api/settings/transfer", content_type="application/json")
        assert response.status_code == 400

    def test_put_settings_missing_settings_key(self, client):
        """Test PUT without settings key."""
        response = client.put(
            "/api/settings/transfer",
            json={"concurrency": 3},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "settings" in data["error"].lower()

    def test_put_settings_validation_error_concurrency(self, client):
        """Test validation error for invalid concurrency."""
        response = client.put(
            "/api/settings/transfer",
            json={"settings": {"concurrency": 100}},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["error"] == "validation_error"
        assert "concurrency" in data["fields"]

    def test_put_settings_validation_error_template(self, client):
        """Test validation error for invalid template variable."""
        response = client.put(
            "/api/settings/transfer",
            json={"settings": {"naming": {"title_template": "{invalid_var}"}}},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["error"] == "validation_error"
        assert "naming.title_template" in data["fields"]

    def test_put_settings_validation_error_privacy(self, client):
        """Test validation error for invalid privacy value."""
        response = client.put(
            "/api/settings/transfer",
            json={"settings": {"privacy": {"visibility": "invalid"}}},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["error"] == "validation_error"
        assert "privacy.visibility" in data["fields"]

    def test_put_settings_partial_update(self, client):
        """Test that partial updates merge with defaults."""
        response = client.put(
            "/api/settings/transfer",
            json={"settings": {"concurrency": 4}},
            content_type="application/json",
        )
        assert response.status_code == 200

        data = response.get_json()
        # Should have the updated value
        assert data["settings"]["concurrency"] == 4
        # Should still have defaults for other fields
        assert data["settings"]["retry"]["max_attempts"] == 3


class TestPreviewTransferSettings:
    """Tests for POST /api/settings/transfer/preview."""

    def test_preview_success(self, client):
        """Test successful preview."""
        response = client.post(
            "/api/settings/transfer/preview",
            json={
                "activity": {
                    "labelId": "test123",
                    "sportType": 100,
                    "name": "Morning Run",
                    "startTime": "2024-01-15 08:30:00",
                    "duration": 3600,
                    "distance": 10000,
                }
            },
            content_type="application/json",
        )
        assert response.status_code == 200

        data = response.get_json()
        assert "rendered" in data
        assert "patch" in data
        assert "title" in data["rendered"]
        # sportType 100 = 跑步
        assert "跑步" in data["rendered"]["title"]
        assert "2024-01-15" in data["rendered"]["title"]

    def test_preview_with_custom_settings(self, client):
        """Test preview with custom settings override."""
        response = client.post(
            "/api/settings/transfer/preview",
            json={
                "activity": {
                    "labelId": "test123",
                    "sportType": 200,  # 骑行
                    "name": "Bike Ride",
                    "startTime": "2024-01-20 14:00:00",
                    "distance": 30000,
                },
                "settings": {
                    "naming": {
                        "title_template": "{sport} {distance_km}km",
                        "description_template": "Synced from COROS",
                    }
                },
            },
            content_type="application/json",
        )
        assert response.status_code == 200

        data = response.get_json()
        assert "骑行" in data["rendered"]["title"]
        assert "30" in data["rendered"]["title"]  # 30km
        assert data["rendered"]["description"] == "Synced from COROS"

    def test_preview_missing_activity(self, client):
        """Test preview without activity."""
        response = client.post(
            "/api/settings/transfer/preview",
            json={},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        # Either "activity" or "request body" in error message
        assert "activity" in data["error"].lower() or "required" in data["error"].lower()

    def test_preview_patch_includes_metadata(self, client):
        """Test that preview patch includes intended metadata operations."""
        # First set up settings with gear
        client.put(
            "/api/settings/transfer",
            json={
                "settings": {
                    "privacy": {"visibility": "private"},
                    "gear": {"enabled": True, "gear_id": "gear-uuid-123"},
                }
            },
            content_type="application/json",
        )

        response = client.post(
            "/api/settings/transfer/preview",
            json={
                "activity": {
                    "labelId": "test123",
                    "sportType": 100,
                    "startTime": "2024-01-15 08:30:00",
                }
            },
            content_type="application/json",
        )
        assert response.status_code == 200

        data = response.get_json()
        patch = data["patch"]
        assert "activityName" in patch
        assert "privacy" in patch
        assert patch["privacy"]["typeKey"] == "private"
        assert patch["gear_id"] == "gear-uuid-123"


class TestGarminGearEndpoint:
    """Tests for GET /api/garmin/gear."""

    def test_gear_no_garmin_account(self, client, monkeypatch):
        """Test gear endpoint when Garmin not configured."""
        mock_account_service = MagicMock()
        mock_account_service.get_client.return_value = None
        monkeypatch.setattr(
            "fitness_toolkit.services.account.AccountService.get_client",
            mock_account_service.get_client,
        )

        response = client.get("/api/garmin/gear")
        assert response.status_code == 200

        data = response.get_json()
        assert data["gear"] == []
        assert "warning" in data

    def test_gear_api_error(self, client, monkeypatch):
        """Test gear endpoint when API fails."""
        mock_client = MagicMock()
        mock_account_service = MagicMock()
        mock_account_service.get_client.return_value = mock_client
        monkeypatch.setattr(
            "fitness_toolkit.services.account.AccountService.get_client",
            mock_account_service.get_client,
        )

        # Mock garth.connectapi at the global level
        with patch("garth.connectapi") as mock_connectapi:
            mock_connectapi.side_effect = Exception("API Error")

            response = client.get("/api/garmin/gear")
            assert response.status_code == 200

            data = response.get_json()
            assert data["gear"] == []
            assert "warning" in data

    def test_gear_success(self, client, monkeypatch):
        """Test gear endpoint success."""
        mock_client = MagicMock()
        mock_account_service = MagicMock()
        mock_account_service.get_client.return_value = mock_client
        monkeypatch.setattr(
            "fitness_toolkit.services.account.AccountService.get_client",
            mock_account_service.get_client,
        )

        # Mock garth.connectapi at the global level
        with patch("garth.connectapi") as mock_connectapi:
            mock_connectapi.return_value = [
                {
                    "uuid": "gear-1",
                    "displayName": "Running Shoes",
                    "gearTypeName": "Footwear",
                },
                {
                    "gearPk": "gear-2",
                    "customMakeModel": "Bike",
                    "gearTypeName": "Bicycle",
                },
            ]

            response = client.get("/api/garmin/gear")
            assert response.status_code == 200

            data = response.get_json()
            assert len(data["gear"]) == 2
            assert data["gear"][0]["id"] == "gear-1"
            assert data["gear"][0]["name"] == "Running Shoes"
            assert data["gear"][1]["id"] == "gear-2"


class TestSettingsTabLoads:
    """Test that settings tab is present in UI."""

    def test_settings_tab_in_page(self, client):
        """Test that settings tab button exists."""
        response = client.get("/")
        assert response.status_code == 200
        assert "同步设置".encode() in response.data

    def test_settings_form_elements(self, client):
        """Test that settings form elements exist."""
        response = client.get("/")
        assert response.status_code == 200
        html = response.data.decode()
        assert "title_template" in html
        assert "concurrency" in html
        assert "max_attempts" in html
