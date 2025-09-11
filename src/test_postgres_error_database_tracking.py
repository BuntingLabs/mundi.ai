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
import asyncio


@pytest.mark.anyio
async def test_postgres_error_stored_in_database(auth_client):
    map_response = await auth_client.post(
        "/api/maps/create",
        json={
            "title": "Test Map for Database Error Tracking",
            "description": "Test map to verify error storage in database",
        },
    )
    assert map_response.status_code == 200
    map_data = map_response.json()
    project_id = map_data["project_id"]

    invalid_connection_uri = "postgresql://invalid:invalid@invalid.invalid:5432/invalid"
    add_connection_response = await auth_client.post(
        f"/api/projects/{project_id}/postgis-connections",
        json={
            "connection_uri": invalid_connection_uri,
            "connection_name": "Database Error Test Connection",
        },
    )
    assert add_connection_response.status_code == 200

    await asyncio.sleep(3)

    # Fetch project sources and verify one connection with error
    sources_response = await auth_client.get(f"/api/projects/{project_id}/sources")
    assert sources_response.status_code == 200
    sources = sources_response.json()
    assert len(sources) == 1

    postgres_conn = sources[0]
    assert "last_error_text" in postgres_conn
    assert "last_error_timestamp" in postgres_conn

    error_text = postgres_conn["last_error_text"]
    error_timestamp = postgres_conn["last_error_timestamp"]

    assert error_text is not None
    assert error_timestamp is not None

    assert error_text == "Unexpected error: [Errno -2] Name or service not known"
    assert error_timestamp is not None

    # Verify details via sources endpoint are consistent
    detail_sources_response = await auth_client.get(
        f"/api/projects/{project_id}/sources"
    )
    assert detail_sources_response.status_code == 200
    detail_sources = detail_sources_response.json()
    assert len(detail_sources) == 1
    detail_postgres_conn = detail_sources[0]
    assert detail_postgres_conn["last_error_text"] == error_text
    assert detail_postgres_conn["last_error_timestamp"] is not None
