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
import random
from pathlib import Path
import re


@pytest.fixture
async def test_map_with_coho_layer(auth_client):
    random.seed(42)
    map_response = await auth_client.post(
        "/api/maps/create",
        json={
            "title": "Layer Description Test Map",
        },
    )
    assert map_response.status_code == 200, f"Failed to create map: {map_response.text}"
    map_id = map_response.json()["id"]
    file_path = str(
        Path(__file__).parent.parent.parent / "test_fixtures" / "coho_range.gpkg"
    )
    with open(file_path, "rb") as f:
        layer_response = await auth_client.post(
            f"/api/maps/{map_id}/layers",
            files={"file": ("coho_range.gpkg", f, "application/octet-stream")},
            data={"layer_name": "Coho Salmon Range"},
        )
        assert layer_response.status_code == 200, (
            f"Failed to upload layer: {layer_response.text}"
        )
        layer_data = layer_response.json()
        layer_id = layer_data["id"]
        child_map_id = layer_data["dag_child_map_id"]
        layer_details_response = await auth_client.get(
            f"/api/maps/{child_map_id}/layers"
        )
        assert layer_details_response.status_code == 200
        layers = layer_details_response.json()["layers"]
        assert len(layers) == 1
        layer = layers[0]
        assert layer["type"] == "vector"
        assert layer["feature_count"] is not None
        assert layer["feature_count"] == 677
    return {"map_id": child_map_id, "layer_id": layer_id}


@pytest.mark.anyio
async def test_describe_layer_endpoint(test_map_with_coho_layer, auth_client):
    layer_id = test_map_with_coho_layer["layer_id"]
    response = await auth_client.get(f"/api/layer/{layer_id}/describe")

    # Check that the response is successful
    assert response.status_code == 200, (
        f"Failed to get layer description: {response.text}"
    )
    print(f"Response: {response.text}")

    # Verify the content type
    assert "text/plain" in response.headers["content-type"], (
        "Response is not text/plain"
    )

    # Check for key sections in the markdown output
    content = response.text
    assert "# Layer: Coho Salmon Range" in content, "Missing layer title"
    assert "## Geographic Extent" in content, "Missing geographic extent section"
    assert "## Schema Information" in content, "Missing schema information section"

    # Verify specific data points
    assert f"ID: {layer_id}" in content, "Missing or incorrect layer ID"
    assert "Type: vector" in content, "Missing or incorrect layer type"
    assert "Geometry Type: polygon" in content, "Missing or incorrect geometry type"
    assert "Dataset Bounds: -124.358276,36.943698,-121.809132,42.004503" in content, (
        "Missing or incorrect dataset bounds"
    )
    assert "Feature Count: 677" in content, "Missing or incorrect feature count"
    assert "CRS: EPSG:3857" in content, "Missing or incorrect CRS info"
    assert "Driver: GPKG" in content, "Missing or incorrect driver info"

    # Check for attribute fields
    assert "### Attribute Fields" in content, "Missing attribute fields section"
    assert "#### float" in content, "Missing float type section"
    assert "#### int32" in content, "Missing int32 type section"
    assert "#### str:" in content, "Missing string type section"
    assert "Acreage" in content, "Missing Acreage field"
    assert "Shape__Are" in content, "Missing Shape__Are field"
    assert "Shape__Len" in content, "Missing Shape__Len field"
    assert "OBJECTID" in content, "Missing OBJECTID field"
    assert "CALWNUM" in content, "Missing CALWNUM field"
    assert "Planning_W" in content, "Missing Planning_W field"

    # Check for attribute table section
    assert "## Sampled Features Attribute Table" in content, (
        "Missing attribute table section"
    )
    # Check that it mentions sampling some number of features
    assert re.search(r"Randomly sampled \d+ of 677 features for this table", content), (
        "Missing sampling information"
    )
    assert "Acreage,CALWNUM,OBJECTID,Planning_W,Shape__Are,Shape__Len" in content, (
        "Missing CSV header"
    )

    # Check that CSV data contains expected columns with numeric values
    # Just verify the first row has the expected format
    # Allow for truncated values (ee version truncates at 20 chars)
    assert re.search(
        r"\d+\.\d+,\d+\.\d+,1,S\. Fork Winchuck",
        content,
    ), "CSV data doesn't match expected format"

    # Check for the style section (it uses Style ID format now)
    assert "## Style ID" in content
    # Check for specific style JSON elements without checking the full structure
    # since the layer ID is random
    assert '"type": "fill"' in content, "Missing fill layer type"
    assert '"type": "line"' in content, "Missing line layer type"
    assert '"fill-color": "#FF6B6B"' in content, "Missing fill color"
    assert '"fill-opacity":' in content, "Missing fill opacity"
    assert '"fill-outline-color": "#000"' in content, "Missing fill outline color"
    assert '"line-color":' in content, "Missing line color"
    assert '"line-width": 1' in content, "Missing line width"


@pytest.fixture
async def test_map_with_point_cloud_layer(auth_client):
    random.seed(42)
    map_response = await auth_client.post(
        "/api/maps/create",
        json={
            "title": "Point Cloud Layer Description Test Map",
        },
    )
    assert map_response.status_code == 200, f"Failed to create map: {map_response.text}"
    map_id = map_response.json()["id"]
    file_path = str(
        Path(__file__).parent.parent.parent / "test_fixtures" / "whitney_pc.laz"
    )
    with open(file_path, "rb") as f:
        layer_response = await auth_client.post(
            f"/api/maps/{map_id}/layers",
            files={"file": ("whitney_pc.laz", f, "application/octet-stream")},
            data={"layer_name": "Whitney Point Cloud"},
        )
        assert layer_response.status_code == 200, (
            f"Failed to upload layer: {layer_response.text}"
        )
        layer_data = layer_response.json()
        layer_id = layer_data["id"]
        new_map_id = layer_data["dag_child_map_id"]
        layer_details_response = await auth_client.get(f"/api/maps/{new_map_id}/layers")
        assert layer_details_response.status_code == 200
        layers = layer_details_response.json()["layers"]
        assert len(layers) == 1
        layer = layers[0]
        assert layer["type"] == "point_cloud"
    return {"map_id": new_map_id, "layer_id": layer_id}


@pytest.mark.anyio
async def test_describe_point_cloud_layer_endpoint(
    test_map_with_point_cloud_layer, auth_client
):
    layer_id = test_map_with_point_cloud_layer["layer_id"]
    response = await auth_client.get(f"/api/layer/{layer_id}/describe")

    # Check that the response is successful
    assert response.status_code == 200, (
        f"Failed to get layer description: {response.text}"
    )

    # Verify the content type
    assert "text/plain" in response.headers["content-type"], (
        "Response is not text/plain"
    )

    # Check for key sections in the markdown output
    content = response.text
    print(content)
    assert "# Layer: Whitney Point Cloud" in content, "Missing layer title"
    assert "Created On:" in content, "Missing created on section"
    assert "Last Edited:" in content, "Missing last edited section"

    # Verify specific data points
    assert f"ID: {layer_id}" in content, "Missing or incorrect layer ID"
    assert "Type: point_cloud" in content, "Missing or incorrect layer type"

    # Check for geographic extent and bounds formatting (3 decimal places)
    assert "## Geographic Extent" in content, "Missing geographic extent section"
    assert "-118.296" in content, "Missing bounds value -118.296"
    assert "36.570" in content, "Missing bounds value 36.570"
    assert "-118.285" in content, "Missing bounds value -118.285"
    assert "36.579" in content, "Missing bounds value 36.579"


@pytest.mark.anyio
async def test_describe_layer_not_found(auth_client):
    response = await auth_client.get("/api/layer/L123456789012/describe")

    # Should get a 404 Not Found response
    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
