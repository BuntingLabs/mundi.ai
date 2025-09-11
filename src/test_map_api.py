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
async def test_create_map(auth_client):
    payload = {
        "title": "Test Map API",
    }
    response = await auth_client.post(
        "/api/maps/create",
        json=payload,
    )
    if response.status_code != 200:
        print(f"Response: {response.status_code}")
        print(f"Error response: {response.text}")
        print(f"Headers: {response.headers}")
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["title"] == "Test Map API"
    assert "created_on" in data
    assert "map_link" in data


@pytest.mark.anyio
async def test_style_json_nonexistent_map(auth_client):
    response = await auth_client.get("/api/maps/foobar/style.json")
    assert response.status_code == 404
    error_data = response.json()
    assert "detail" in error_data
    assert "not found" in error_data["detail"].lower()
