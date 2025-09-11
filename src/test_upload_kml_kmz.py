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
import time


@pytest.fixture
async def test_map_id(auth_client):
    payload = {
        "title": "Upload KML/KMZ Test Map",
        "description": "Test map for KML and KMZ file upload",
    }

    response = await auth_client.post(
        "/api/maps/create",
        json=payload,
    )

    assert response.status_code == 200, f"Failed to create map: {response.text}"
    map_id = response.json()["id"]

    return map_id


@pytest.mark.anyio
async def test_upload_kml(test_map_id, auth_client):
    file_path = "test_fixtures/VancouverNeighborhoods.kml"

    with open(file_path, "rb") as f:
        files = {"file": ("VancouverNeighborhoods.kml", f)}
        data = {
            "layer_name": "Vancouver Neighborhoods KML",
        }

        response = await auth_client.post(
            f"/api/maps/{test_map_id}/layers",
            files=files,
            data=data,
        )

        assert response.status_code == 200, f"Failed to upload KML: {response.text}"
        response_data = response.json()
        layer_id = response_data["id"]
        dag_child_map_id = response_data["dag_child_map_id"]

    response = await auth_client.get(
        f"/api/maps/{dag_child_map_id}/layers",
    )
    assert response.status_code == 200, f"Failed to get layers: {response.text}"
    layers_response = response.json()

    layers = layers_response["layers"]

    assert any(layer["id"] == layer_id for layer in layers), (
        "KML layer was not added to map"
    )

    layer_data = next(layer for layer in layers if layer["id"] == layer_id)
    assert layer_data["name"] == "Vancouver Neighborhoods KML"

    response = await auth_client.get(
        f"/api/layer/{layer_id}.geojson",
    )

    assert response.status_code == 200, f"Failed to access layer: {response.text}"
    assert response.headers["Content-Type"] == "application/geo+json"

    geojson = response.json()
    assert "features" in geojson
    assert len(geojson["features"]) == 6

    for feature in geojson["features"]:
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Polygon"
        assert "coordinates" in feature["geometry"]
        assert len(feature["geometry"]["coordinates"]) >= 1


@pytest.mark.anyio
async def test_upload_kmz(test_map_id, auth_client):
    file_path = "test_fixtures/VancouverNeighborhoods.kmz"

    with open(file_path, "rb") as f:
        files = {"file": ("VancouverNeighborhoods.kmz", f)}
        data = {
            "layer_name": "Vancouver Neighborhoods KMZ",
        }

        response = await auth_client.post(
            f"/api/maps/{test_map_id}/layers",
            files=files,
            data=data,
        )

        assert response.status_code == 200, f"Failed to upload KMZ: {response.text}"
        response_data = response.json()
        layer_id = response_data["id"]
        dag_child_map_id = response_data["dag_child_map_id"]

    response = await auth_client.get(
        f"/api/maps/{dag_child_map_id}/layers",
    )
    assert response.status_code == 200, f"Failed to get layers: {response.text}"
    layers_response = response.json()

    layers = layers_response["layers"]

    assert any(layer["id"] == layer_id for layer in layers), (
        "KMZ layer was not added to map"
    )

    layer_data = next(layer for layer in layers if layer["id"] == layer_id)
    assert layer_data["name"] == "Vancouver Neighborhoods KMZ"

    response = await auth_client.get(
        f"/api/layer/{layer_id}.geojson",
    )

    assert response.status_code == 200, f"Failed to access layer: {response.text}"
    assert response.headers["Content-Type"] == "application/geo+json"

    geojson = response.json()
    assert "features" in geojson
    assert len(geojson["features"]) == 6

    for feature in geojson["features"]:
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Polygon"
        assert "coordinates" in feature["geometry"]
        assert len(feature["geometry"]["coordinates"]) >= 1


@pytest.mark.anyio
async def test_upload_ukraine_fgb_timed(test_map_id, auth_client):
    file_path = "test_fixtures/ukraine.fgb"

    start_time = time.time()

    with open(file_path, "rb") as f:
        files = {"file": ("ukraine.fgb", f)}
        data = {
            "layer_name": "Ukraine FGB Layer",
        }

        response = await auth_client.post(
            f"/api/maps/{test_map_id}/layers",
            files=files,
            data=data,
        )

    end_time = time.time()
    upload_duration = end_time - start_time

    assert upload_duration < 10.0, (
        f"Upload took {upload_duration:.2f} seconds, expected under 10 seconds"
    )
    assert response.status_code == 200, f"Failed to upload FGB: {response.text}"

    response_data = response.json()
    layer_id = response_data["id"]

    response = await auth_client.get(
        f"/api/layer/{layer_id}.pmtiles",
    )

    assert response.status_code == 200, f"Failed to access pmtiles: {response.text}"


@pytest.mark.anyio
async def test_upload_singlepoint_fgb_timed(test_map_id, auth_client):
    file_path = "test_fixtures/singlepoint.fgb"

    start_time = time.time()

    with open(file_path, "rb") as f:
        files = {"file": ("singlepoint.fgb", f)}
        data = {
            "layer_name": "Single Point FGB Layer",
        }

        response = await auth_client.post(
            f"/api/maps/{test_map_id}/layers",
            files=files,
            data=data,
        )

    end_time = time.time()
    upload_duration = end_time - start_time

    assert upload_duration < 10.0, (
        f"Upload took {upload_duration:.2f} seconds, expected under 10 seconds"
    )
    assert response.status_code == 200, f"Failed to upload FGB: {response.text}"

    response_data = response.json()
    layer_id = response_data["id"]

    response = await auth_client.get(
        f"/api/layer/{layer_id}.pmtiles",
    )

    assert response.status_code == 200, f"Failed to access pmtiles: {response.text}"
