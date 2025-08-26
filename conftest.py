# Copyright (C) 2025 Bunting Labs, Inc.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import pytest
import os

# Set fast timeout for postgres connections in tests
os.environ["MUNDI_POSTGIS_TIMEOUT_SEC"] = "0.5"
from httpx_ws.transport import ASGIWebSocketTransport
from httpx import AsyncClient
from pathlib import Path
import random
import asyncio
from concurrent.futures import ThreadPoolExecutor
from starlette.testclient import TestClient
from alembic import command
from alembic.config import Config

from src.wsgi import app


@pytest.fixture
def run_alembic_operation():
    async def _run_alembic_operation(operation, target=None):
        project_root = Path(__file__).parent
        alembic_cfg = Config(project_root / "alembic.ini")
        alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))

        def run_operation():
            if operation == "upgrade":
                command.upgrade(alembic_cfg, target or "head")
            elif operation == "downgrade":
                command.downgrade(alembic_cfg, target)
            else:
                raise ValueError(f"Unknown operation: {operation}")

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            await loop.run_in_executor(executor, run_operation)

    return _run_alembic_operation


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
@pytest.mark.anyio
async def client():
    # Run database migrations before tests
    from src.database.migrate import run_migrations

    await run_migrations()

    transport = ASGIWebSocketTransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(scope="session")
async def auth_client(client):
    assert os.environ.get("MUNDI_AUTH_MODE") == "edit"

    yield client


@pytest.fixture(scope="session")
async def test_map_with_vector_layers(auth_client):
    map_payload = {
        "title": "Geoprocessing Test Map",
        "description": "Test map for geoprocessing operations with vector layers",
    }
    map_response = await auth_client.post("/api/maps/create", json=map_payload)
    assert map_response.status_code == 200, f"Failed to create map: {map_response.text}"
    current_map_id = map_response.json()["id"]
    layer_ids = {}

    async def _upload_layer(file_name, layer_name_in_db, target_map_id):
        file_path = str(Path(__file__).parent / "test_fixtures" / file_name)
        if not os.path.exists(file_path):
            pytest.skip(f"Test file {file_path} not found")
        with open(file_path, "rb") as f:
            layer_response = await auth_client.post(
                f"/api/maps/{target_map_id}/layers",
                files={"file": (file_name, f, "application/octet-stream")},
                data={"layer_name": layer_name_in_db},
            )
            assert layer_response.status_code == 200, (
                f"Failed to upload layer {file_name}: {layer_response.text}"
            )
            response_data = layer_response.json()
            print(response_data)
            return response_data["id"], response_data["dag_child_map_id"]

    random.seed(42)
    layer_id, current_map_id = await _upload_layer(
        "barcelona_beaches.fgb", "Barcelona Beaches", current_map_id
    )
    layer_ids["beaches_layer_id"] = layer_id

    layer_id, current_map_id = await _upload_layer(
        "barcelona_cafes.fgb", "Barcelona Cafes", current_map_id
    )
    layer_ids["cafes_layer_id"] = layer_id

    layer_id, current_map_id = await _upload_layer(
        "idaho_weatherstations.geojson", "Idaho Weather Stations", current_map_id
    )
    layer_ids["idaho_stations_layer_id"] = layer_id

    return {
        "map_id": current_map_id,
        "project_id": map_response.json()["project_id"],
        **layer_ids,
    }


@pytest.fixture
async def test_project_with_multiple_origins(auth_client):
    """Create a test project for testing multiple origin domains."""
    project_payload = {"layers": []}
    map_create_payload = {
        "project": project_payload,
        "title": "Test Project for Multiple Origins",
        "description": "A test project for testing multiple allowed origins",
    }
    response = await auth_client.post("/api/maps/create", json=map_create_payload)
    assert response.status_code == 200
    return response.json()


@pytest.fixture(scope="function")
def sync_client():
    # Run database migrations before tests
    from src.database.migrate import run_migrations

    asyncio.run(run_migrations())

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="function")
def sync_auth_client(sync_client):
    assert os.environ.get("MUNDI_AUTH_MODE") == "edit"
    yield sync_client


@pytest.fixture
def websocket_url_for_map(sync_auth_client):
    def _get_url(map_id, conversation_id):
        return f"/api/maps/ws/{conversation_id}/messages/updates"

    return _get_url


@pytest.fixture
async def test_project(auth_client):
    project_payload = {"layers": []}
    map_create_payload = {
        "project": project_payload,
        "title": "Test Project",
        "description": "A test project",
    }

    response = await auth_client.post("/api/maps/create", json=map_create_payload)
    assert response.status_code == 200
    map_data = response.json()
    return {"project_id": map_data["project_id"], "map_id": map_data["id"]}


@pytest.fixture
async def test_project_with_map(auth_client):
    project_payload = {"layers": []}
    map_create_payload = {
        "project": project_payload,
        "title": "Test Project with Map",
        "description": "A test project with map",
    }

    response = await auth_client.post("/api/maps/create", json=map_create_payload)
    assert response.status_code == 200
    map_data = response.json()
    return {"project_id": map_data["project_id"], "map_id": map_data["id"]}


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "s3: mark test as requiring S3/MinIO access")
    config.addinivalue_line(
        "markers", "postgres: mark test as requiring PostgreSQL access"
    )
    config.addinivalue_line("markers", "anyio: mark a test as asynchronous using AnyIO")

    # monkey patch ssl.create_default_context to use a cached version
    # ssl.py create_default_context takes a HUGE amount of time with openssl v3.0.0,
    # and it's a known issue: https://github.com/python/cpython/issues/95031
    # https://github.com/psf/requests/pull/6667
    # https://github.com/boto/botocore/issues/3171
    # this saves like 10 seconds of clock time on tests...
    import ssl
    from functools import lru_cache

    original_create_default_context = ssl.create_default_context

    @lru_cache(maxsize=8)
    def cached_create_default_context(*args, **kwargs):
        return original_create_default_context(*args, **kwargs)

    ssl.create_default_context = cached_create_default_context
