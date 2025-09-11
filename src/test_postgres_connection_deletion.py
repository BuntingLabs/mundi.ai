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


@pytest.mark.anyio
async def test_soft_delete_postgis_connection_as_owner(auth_client):
    """Test that project owners can soft delete postgres connections"""

    # Create project
    map_response = await auth_client.post(
        "/api/maps/create",
        json={
            "title": "Test Map for Connection Deletion",
            "description": "Test project for postgres connection deletion",
        },
    )
    assert map_response.status_code == 200
    project_id = map_response.json()["project_id"]

    # Add postgres connection
    add_response = await auth_client.post(
        f"/api/projects/{project_id}/postgis-connections",
        json={
            "connection_uri": "postgresql://test:test@example.com:5432/testdb",
            "connection_name": "Test Connection for Deletion",
        },
    )
    assert add_response.status_code == 200

    # Get connection ID from project sources
    sources_response = await auth_client.get(f"/api/projects/{project_id}/sources")
    assert sources_response.status_code == 200
    sources = sources_response.json()
    assert len(sources) == 1
    connection_id = sources[0]["connection_id"]

    # Soft delete the connection
    delete_response = await auth_client.delete(
        f"/api/projects/{project_id}/postgis-connections/{connection_id}"
    )
    assert delete_response.status_code == 200
    delete_data = delete_response.json()
    assert delete_data["success"] is True
    assert "deleted successfully" in delete_data["message"]

    # Verify connection no longer appears in project sources
    sources_response_after = await auth_client.get(
        f"/api/projects/{project_id}/sources"
    )
    assert sources_response_after.status_code == 200
    sources_after = sources_response_after.json()
    assert len(sources_after) == 0


@pytest.mark.anyio
async def test_soft_delete_nonexistent_connection(auth_client):
    """Test deleting non-existent connection returns 404"""

    # Create project
    map_response = await auth_client.post(
        "/api/maps/create",
        json={
            "title": "Test Map for Nonexistent Connection",
            "description": "Test project for nonexistent connection deletion",
        },
    )
    assert map_response.status_code == 200
    project_id = map_response.json()["project_id"]

    # Try to delete non-existent connection
    fake_connection_id = "C123456789ab"
    delete_response = await auth_client.delete(
        f"/api/projects/{project_id}/postgis-connections/{fake_connection_id}"
    )
    assert delete_response.status_code == 404
    delete_data = delete_response.json()
    assert "not found" in delete_data["detail"]


@pytest.mark.anyio
async def test_soft_delete_already_deleted_connection(auth_client):
    """Test that deleting already soft-deleted connection returns 409"""

    # Create project
    map_response = await auth_client.post(
        "/api/maps/create",
        json={
            "title": "Test Map for Double Deletion",
            "description": "Test project for double deletion",
        },
    )
    assert map_response.status_code == 200
    project_id = map_response.json()["project_id"]

    # Add postgres connection
    add_response = await auth_client.post(
        f"/api/projects/{project_id}/postgis-connections",
        json={
            "connection_uri": "postgresql://test:test@example.com:5432/testdb",
            "connection_name": "Test Connection for Double Deletion",
        },
    )
    assert add_response.status_code == 200

    # Get connection ID from project sources
    sources_response = await auth_client.get(f"/api/projects/{project_id}/sources")
    assert sources_response.status_code == 200
    sources = sources_response.json()
    assert len(sources) == 1
    connection_id = sources[0]["connection_id"]

    # First deletion should succeed
    delete_response_1 = await auth_client.delete(
        f"/api/projects/{project_id}/postgis-connections/{connection_id}"
    )
    assert delete_response_1.status_code == 200

    # Second deletion should fail with 409 conflict
    delete_response_2 = await auth_client.delete(
        f"/api/projects/{project_id}/postgis-connections/{connection_id}"
    )
    assert delete_response_2.status_code == 409
    delete_data = delete_response_2.json()
    assert "already deleted" in delete_data["detail"]


@pytest.mark.anyio
async def test_soft_delete_nonexistent_project(auth_client):
    """Test deleting connection from non-existent project returns 404"""

    fake_project_id = "P123456789ab"
    fake_connection_id = "C123456789ab"

    delete_response = await auth_client.delete(
        f"/api/projects/{fake_project_id}/postgis-connections/{fake_connection_id}"
    )
    assert delete_response.status_code == 404
    delete_data = delete_response.json()
    assert "not found" in delete_data["detail"]


@pytest.mark.anyio
async def test_soft_deleted_connection_not_listed(auth_client):
    """Test that soft deleted connections don't appear in project listings"""

    # Create project
    map_response = await auth_client.post(
        "/api/maps/create",
        json={
            "title": "Test Map for Connection Listing",
            "description": "Test project for connection listing after deletion",
        },
    )
    assert map_response.status_code == 200
    project_id = map_response.json()["project_id"]

    # Add two postgres connections
    add_response_1 = await auth_client.post(
        f"/api/projects/{project_id}/postgis-connections",
        json={
            "connection_uri": "postgresql://test1:test@example.com:5432/testdb1",
            "connection_name": "Connection 1",
        },
    )
    assert add_response_1.status_code == 200

    add_response_2 = await auth_client.post(
        f"/api/projects/{project_id}/postgis-connections",
        json={
            "connection_uri": "postgresql://test2:test@example.com:5432/testdb2",
            "connection_name": "Connection 2",
        },
    )
    assert add_response_2.status_code == 200

    # Verify both connections are listed
    sources_response = await auth_client.get(f"/api/projects/{project_id}/sources")
    assert sources_response.status_code == 200
    sources = sources_response.json()
    assert len(sources) == 2

    # Get first connection ID and delete it
    connection_id_1 = sources[0]["connection_id"]
    delete_response = await auth_client.delete(
        f"/api/projects/{project_id}/postgis-connections/{connection_id_1}"
    )
    assert delete_response.status_code == 200

    # Verify only one connection is now listed
    sources_response_after = await auth_client.get(
        f"/api/projects/{project_id}/sources"
    )
    assert sources_response_after.status_code == 200
    sources_after = sources_response_after.json()
    assert len(sources_after) == 1
    # Verify the remaining connection is the second one
    remaining_connection = sources_after[0]
    assert remaining_connection["friendly_name"] == "Connection 2"
