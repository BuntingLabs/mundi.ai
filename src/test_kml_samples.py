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


@pytest.fixture
async def test_map_id(auth_client):
    payload = {
        "title": "KML Samples Test Map",
        "description": "Test map for multi-layer KML upload",
    }

    response = await auth_client.post(
        "/api/maps/create",
        json=payload,
    )

    assert response.status_code == 200, f"Failed to create map: {response.text}"
    data = response.json()
    return data["id"]


@pytest.mark.anyio
async def test_upload_kml_samples_creates_multiple_layers(test_map_id, auth_client):
    file_path = "test_fixtures/KML_Samples.kml"

    # Do not pass a layer_name to ensure sublayer names are used as-is
    with open(file_path, "rb") as f:
        files = {"file": ("KML_Samples.kml", f)}
        data = {}

        response = await auth_client.post(
            f"/api/maps/{test_map_id}/layers",
            files=files,
            data=data,
        )

    assert response.status_code == 200, f"Failed to upload KML: {response.text}"
    result = response.json()
    dag_child_map_id = result["dag_child_map_id"]

    # Fetch layers for the resulting map version
    layers_resp = await auth_client.get(f"/api/maps/{dag_child_map_id}/layers")
    assert layers_resp.status_code == 200, f"Failed to list layers: {layers_resp.text}"
    layers_data = layers_resp.json()["layers"]

    # Expect exactly 6 layers from the sample file
    assert len(layers_data) == 6, f"Expected 6 layers, got {len(layers_data)}"

    # Check expected names
    expected_names = {
        "Absolute and Relative",
        "Highlighted Icon",
        "Google Campus",
        "Extruded Polygon",
        "Placemarks",
        "Paths",
    }
    for name in expected_names:
        assert any(name in lyr["name"] for lyr in layers_data), (
            f"Expected sublayer {name} not found"
        )

    # Validate geometry type counts (2 points, 1 linestring, 3 polygons)
    def normalize_geom(gt: str | None) -> str:
        gt = (gt or "").lower()
        if gt in ("point", "multipoint"):
            return "point"
        if gt in ("linestring", "multilinestring"):
            return "linestring"
        return "polygon"  # default remaining to polygon/multipolygon

    counts = {"point": 0, "linestring": 0, "polygon": 0}
    for lyr in layers_data:
        counts[normalize_geom(lyr.get("geometry_type"))] += 1

    assert counts["point"] == 2, f"Expected 2 point layers, got {counts['point']}"
    assert counts["linestring"] == 1, (
        f"Expected 1 linestring layer, got {counts['linestring']}"
    )
    assert counts["polygon"] == 3, f"Expected 3 polygon layers, got {counts['polygon']}"
