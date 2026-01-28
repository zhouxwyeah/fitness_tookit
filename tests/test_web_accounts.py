"""Tests for web account management."""

import pytest
from fitness_toolkit.web.app import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_index_page(client):
    """Test index page loads successfully."""
    response = client.get('/')
    assert response.status_code == 200
    assert b'Fitness Toolkit' in response.data
    assert '账号管理'.encode('utf-8') in response.data
    assert '下载数据'.encode('utf-8') in response.data
    assert '定时任务'.encode('utf-8') in response.data


def test_list_accounts_api(client):
    """Test list accounts API."""
    response = client.get('/api/accounts')
    assert response.status_code == 200
    data = response.get_json()
    assert 'accounts' in data
    assert isinstance(data['accounts'], list)
