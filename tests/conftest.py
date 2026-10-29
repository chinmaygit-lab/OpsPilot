import pytest
from fastapi.testclient import TestClient
from opspilot.api import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "app.sqlite"), demo_mode=True)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def acme_headers():
    return {"X-API-Key": "demo-acme-owner"}


@pytest.fixture
def nova_headers():
    return {"X-API-Key": "demo-nova-owner"}


@pytest.fixture
def viewer_headers():
    return {"X-API-Key": "demo-acme-viewer"}
