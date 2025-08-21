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
async def test_remote_file_with_pmtiles_generation(auth_client):
    """Test remote file processing with PMTiles generation."""
    remote_url = "https://github.com/BuntingLabs/mundi.ai/raw/aa187476cbbbc03273d303a8ba34eb546a2df1de/test_fixtures/airports.geojson"

    map_response = await auth_client.post(
        "/api/maps/create", json={"name": "Test Map for Remote File"}
    )
    assert map_response.status_code == 200
    map_id = map_response.json()["id"]

    response = await auth_client.post(
        f"/api/maps/{map_id}/layers/remote",
        json={
            "url": remote_url,
            "name": "Test Remote GeoJSON Layer",
            "source_type": "vector",
        },
    )

    if response.status_code != 200:
        print(f"Error response: {response.status_code} - {response.text}")
    assert response.status_code == 200

    layer_id = response.json()["id"]
    layer_type = response.json()["type"]
    assert layer_type == "vector"

    await asyncio.sleep(10)

    pmtiles_response = await auth_client.get(f"/api/layer/{layer_id}.pmtiles")
    if pmtiles_response.status_code != 200:
        print(
            f"PMTiles request failed: {pmtiles_response.status_code} - {pmtiles_response.text}"
        )
    assert pmtiles_response.status_code == 200
    assert len(pmtiles_response.content) > 0, "PMTiles content should not be empty"

    # PMTiles v3 format starts with 'PMTi' (0x504d5469)
    assert pmtiles_response.content[:4] == b"PMTi", (
        f"Invalid PMTiles file signature: {pmtiles_response.content[:4]}"
    )

    response_data = response.json()
    assert "id" in response_data
    assert "name" in response_data
    assert "type" in response_data
    assert "url" in response_data
    assert response_data["name"] == "Test Remote GeoJSON Layer"

    print(f"Remote file layer created successfully with ID: {layer_id}")
    print(f"PMTiles generated and accessible ({len(pmtiles_response.content)} bytes)")


@pytest.mark.anyio
async def test_google_sheets_with_pmtiles_generation(auth_client):
    """Test Google Sheets processing with PMTiles generation."""
    expected_csv_url = "CSV:/vsicurl/https://docs.google.com/spreadsheets/d/1vsHncOHn0l5uk29zFYG9HvAMHMS1tanXJKKsMCs2hkw/export?format=csv&id=1vsHncOHn0l5uk29zFYG9HvAMHMS1tanXJKKsMCs2hkw&gid=0"

    map_response = await auth_client.post(
        "/api/maps/create", json={"name": "Test Map for Google Sheets"}
    )
    assert map_response.status_code == 200
    map_id = map_response.json()["id"]

    response = await auth_client.post(
        f"/api/maps/{map_id}/layers/remote",
        json={
            "url": expected_csv_url,
            "name": "Test Google Sheets Layer",
            "source_type": "sheets",
            "add_layer_to_map": True,
        },
    )

    if response.status_code != 200:
        print(f"Error response: {response.status_code} - {response.text}")
    assert response.status_code == 200

    response_data = response.json()
    layer_id = response_data["id"]
    layer_type = response_data["type"]
    assert layer_type == "vector"

    await asyncio.sleep(8)

    pmtiles_response = await auth_client.get(f"/api/layer/{layer_id}.pmtiles")
    assert pmtiles_response.status_code == 200
    assert len(pmtiles_response.content) > 0, "PMTiles content should not be empty"

    # PMTiles v3 format starts with 'PMTi' (0x504d5469)
    assert pmtiles_response.content[:4] == b"PMTi", (
        f"Invalid PMTiles file signature: {pmtiles_response.content[:4]}"
    )

    assert "id" in response_data
    assert "name" in response_data
    assert "type" in response_data
    assert "url" in response_data
    assert response_data["name"] == "Test Google Sheets Layer"

    print(f"Google Sheets layer created successfully with ID: {layer_id}")
    print(f"PMTiles generated and accessible ({len(pmtiles_response.content)} bytes)")


@pytest.mark.anyio
async def test_wfs_with_pmtiles_generation(auth_client):
    """Test WFS processing with PMTiles generation."""
    wfs_url = "https://geo.stat.fi/geoserver/wfs?service=WFS&version=2.0.0&request=GetFeature&typename=vaestoruutu:vaki2021_5km&maxfeatures=10"

    map_response = await auth_client.post(
        "/api/maps/create", json={"name": "Test Map for WFS Layer"}
    )
    assert map_response.status_code == 200
    map_id = map_response.json()["id"]

    response = await auth_client.post(
        f"/api/maps/{map_id}/layers/remote",
        json={
            "url": wfs_url,
            "name": "Test WFS Population Layer",
            "source_type": "vector",
            "add_layer_to_map": True,
        },
    )

    if response.status_code != 200:
        print(f"Error response: {response.status_code} - {response.text}")
        print(f"WFS URL used: {wfs_url}")
    assert response.status_code == 200

    response_data = response.json()
    layer_id = response_data["id"]
    layer_type = response_data["type"]
    assert layer_type == "vector"

    await asyncio.sleep(10)

    pmtiles_response = await auth_client.get(f"/api/layer/{layer_id}.pmtiles")
    assert pmtiles_response.status_code == 200
    assert len(pmtiles_response.content) > 0, "PMTiles content should not be empty"

    # PMTiles v3 format starts with 'PMTi' (0x504d5469)
    assert pmtiles_response.content[:4] == b"PMTi", (
        f"Invalid PMTiles file signature: {pmtiles_response.content[:4]}"
    )

    geojson_response = await auth_client.get(f"/api/layer/{layer_id}.geojson")
    assert geojson_response.status_code == 200
    assert geojson_response.headers["content-type"] == "application/geo+json"
    assert len(geojson_response.content) > 0, "GeoJSON content should not be empty"

    import json

    geojson_data = json.loads(geojson_response.content)
    assert "type" in geojson_data
    assert geojson_data["type"] == "FeatureCollection"
    assert "features" in geojson_data

    assert "id" in response_data
    assert "name" in response_data
    assert "type" in response_data
    assert "url" in response_data
    assert response_data["name"] == "Test WFS Population Layer"

    print(f"WFS layer created successfully with ID: {layer_id}")
    print(f"PMTiles generated and accessible ({len(pmtiles_response.content)} bytes)")
    print(f"GeoJSON contains {len(geojson_data['features'])} features")
