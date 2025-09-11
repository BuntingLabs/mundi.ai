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
import json
from pathlib import Path


@pytest.fixture
async def test_map_with_layer(auth_client):
    map_response = await auth_client.post(
        "/api/maps/create",
        json={
            "title": "Geoprocessing Test Map",
        },
    )
    assert map_response.status_code == 200, f"Failed to create map: {map_response.text}"
    map_id = map_response.json()["id"]

    file_path = str(
        Path(__file__).parent.parent.parent / "test_fixtures" / "UScounties.gpkg"
    )

    if not os.path.exists(file_path):
        pytest.skip(f"Test file {file_path} not found")

    with open(file_path, "rb") as f:
        files = {"file": ("UScounties.gpkg", f)}
        data = {"layer_name": "UScounties"}

        layer_response = await auth_client.post(
            f"/api/maps/{map_id}/layers", files=files, data=data
        )

        assert layer_response.status_code == 200, (
            f"Failed to upload layer: {layer_response.text}"
        )
        layer_id = layer_response.json()["id"]

    return {"map_id": map_id, "layer_id": layer_id}


@pytest.fixture
async def test_map_with_airports_layer(auth_client):
    map_response = await auth_client.post(
        "/api/maps/create",
        json={
            "title": "Airports Test Map",
        },
    )
    assert map_response.status_code == 200, f"Failed to create map: {map_response.text}"
    map_id = map_response.json()["id"]

    file_path = str(
        Path(__file__).parent.parent.parent / "test_fixtures" / "airports.fgb"
    )

    if not os.path.exists(file_path):
        pytest.skip(f"Test file {file_path} not found")

    with open(file_path, "rb") as f:
        files = {"file": ("airports.fgb", f)}
        data = {"layer_name": "Alaska Airports"}

        layer_response = await auth_client.post(
            f"/api/maps/{map_id}/layers", files=files, data=data
        )

        assert layer_response.status_code == 200, (
            f"Failed to upload layer: {layer_response.text}"
        )
        layer_id = layer_response.json()["id"]

    return {"map_id": map_id, "layer_id": layer_id}


@pytest.mark.anyio
async def test_layer_geojson_endpoint(test_map_with_airports_layer, auth_client):
    layer_id = test_map_with_airports_layer["layer_id"]

    response = await auth_client.get(f"/api/layer/{layer_id}.geojson")

    assert response.status_code == 200, f"GeoJSON request failed: {response.text}"
    assert response.headers["Content-Type"] == "application/geo+json"

    geojson_data = json.loads(response.content)

    assert "type" in geojson_data
    assert geojson_data["type"] == "FeatureCollection"
    assert "features" in geojson_data

    assert len(geojson_data["features"]) == 76, (
        f"Expected 76 features, got {len(geojson_data['features'])}"
    )

    longitudes = []
    latitudes = []

    for feature in geojson_data["features"]:
        assert "geometry" in feature
        assert "coordinates" in feature["geometry"]

        coordinates = feature["geometry"]["coordinates"]

        longitudes.append(coordinates[0])
        latitudes.append(coordinates[1])

        assert -180 <= coordinates[0] <= -130, (
            f"Longitude {coordinates[0]} not in Alaska range"
        )

        assert 51 <= coordinates[1] <= 72, (
            f"Latitude {coordinates[1]} not in Alaska range"
        )

    assert -180 <= min(longitudes) <= -130, (
        f"Minimum longitude {min(longitudes)} outside Alaska range"
    )
    assert -180 <= max(longitudes) <= -130, (
        f"Maximum longitude {max(longitudes)} outside Alaska range"
    )
    assert 51 <= min(latitudes) <= 72, (
        f"Minimum latitude {min(latitudes)} outside Alaska range"
    )
    assert 51 <= max(latitudes) <= 72, (
        f"Maximum latitude {max(latitudes)} outside Alaska range"
    )

    sample_feature = geojson_data["features"][0]
    assert "properties" in sample_feature
    assert "NAME" in sample_feature["properties"], "NAME property missing from feature"
