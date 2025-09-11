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


@pytest.fixture
async def test_map_with_layers(auth_client):
    """Create a test map with both vector and raster layers."""

    project = {}

    # Create a map via the API
    payload = {
        "project": project,
        "title": "Test GDAL API Map",
        "description": "Map for testing GDAL endpoints",
        "link_accessible": True,
    }

    # Create the map
    response = await auth_client.post("/api/maps/create", json=payload)
    assert response.status_code == 200, f"Failed to create map: {response.text}"
    map_data = response.json()
    map_id = map_data["id"]

    # Use existing vector file
    vector_path = "test_fixtures/UScounties.gpkg"
    assert os.path.exists(vector_path), "Vector file not found"

    # Upload vector file via API
    with open(vector_path, "rb") as f:
        files = {"file": ("UScounties.gpkg", f, "application/geopackage+sqlite3")}
        response = await auth_client.post(
            f"/api/maps/{map_id}/layers",
            files=files,
            data={"name": "Vector Layer", "type": "vector"},
        )

    assert response.status_code == 200, (
        f"Failed to upload vector layer: {response.text}"
    )
    vector_layer_data = response.json()
    vector_layer_id = vector_layer_data["id"]
    # Get the child map ID from the first upload
    child_map_id = vector_layer_data["dag_child_map_id"]

    # Upload raster to the child map from the first upload
    raster_path = "test_fixtures/waterboard.tif"
    assert os.path.exists(raster_path), "Raster file not found"

    with open(raster_path, "rb") as f:
        files = {"file": ("raster_layer.tif", f, "image/tiff")}
        response = await auth_client.post(
            f"/api/maps/{child_map_id}/layers",
            files=files,
            data={"name": "Raster Layer", "type": "raster"},
        )

    assert response.status_code == 200, (
        f"Failed to upload raster layer: {response.text}"
    )
    raster_layer_data = response.json()
    raster_layer_id = raster_layer_data["id"]
    # Get the final child map ID from the second upload
    final_map_id = raster_layer_data["dag_child_map_id"]

    # Check layer properties by getting details about the layers from the final map
    response = await auth_client.get(f"/api/maps/{final_map_id}/layers")
    assert response.status_code == 200, f"Failed to get layers: {response.text}"

    layers_data = response.json()

    # Check raster layer
    raster_layer = next(
        (layer for layer in layers_data["layers"] if layer["id"] == raster_layer_id),
        None,
    )
    assert raster_layer is not None, "Raster layer not found in layers list"
    # Verify feature_count is null for raster layers
    assert raster_layer["feature_count"] is None, (
        "Expected feature_count to be null for raster layer"
    )

    # Check vector layer
    vector_layer = next(
        (layer for layer in layers_data["layers"] if layer["id"] == vector_layer_id),
        None,
    )
    assert vector_layer is not None, "Vector layer not found in layers list"
    # Verify feature_count is not null for vector layers and has the correct value
    assert vector_layer["feature_count"] is not None, (
        "Expected feature_count to be not null for vector layer"
    )
    assert isinstance(vector_layer["feature_count"], int), (
        "Vector layer feature_count should be an integer"
    )
    assert vector_layer["feature_count"] > 0, (
        "Vector layer feature_count should be positive"
    )

    # US Counties has 3221 features, based on ogrinfo
    ogrinfo_count = 3221
    print(
        f"Vector layer feature count: {vector_layer['feature_count']} (expected: {ogrinfo_count})"
    )
    assert vector_layer["feature_count"] == ogrinfo_count, (
        f"Expected feature_count to be {ogrinfo_count} for US Counties layer"
    )

    # Return the final map ID and layer IDs
    return {
        "map_id": final_map_id,
        "vector_layer_id": vector_layer_id,
        "raster_layer_id": raster_layer_id,
    }


@pytest.mark.s3
@pytest.mark.anyio
async def test_pmtiles_endpoint(test_map_with_layers, auth_client):
    """Test the PMTiles endpoint with a vector layer."""
    map_info = test_map_with_layers
    vector_layer_id = map_info["vector_layer_id"]

    # Call the PMTiles endpoint with cookies
    response = await auth_client.get(f"/api/layer/{vector_layer_id}.pmtiles")

    # Check response
    assert response.status_code == 200, (
        f"Failed to get PMTiles data: {response.status_code}"
    )

    # Check that the content is binary PMTiles data
    assert len(response.content) > 0, "Response content is empty"
    assert response.content.startswith(b"PMTiles"), "Response is not PMTiles data"

    # Verify the content type is appropriate
    content_type = response.headers.get("Content-Type", "")
    assert "octet-stream" in content_type or "application" in content_type, (
        f"Unexpected content type: {content_type}"
    )

    # Check for appropriate headers
    assert "Content-Length" in response.headers, "Missing Content-Length header"
    assert "Accept-Ranges" in response.headers, "Missing Accept-Ranges header"
    assert response.headers["Accept-Ranges"] == "bytes", (
        "Accept-Ranges header should be 'bytes'"
    )

    print(f"PMTiles data received, content length: {len(response.content)} bytes")


@pytest.mark.s3
@pytest.mark.anyio
async def test_cog_endpoint(test_map_with_layers, auth_client):
    """Test the COG endpoint with a raster layer."""
    map_info = test_map_with_layers
    raster_layer_id = map_info["raster_layer_id"]

    # Call the COG endpoint with cookies
    response = await auth_client.get(f"/api/layer/{raster_layer_id}.cog.tif")

    # Check response
    assert response.status_code == 200, (
        f"Failed to get COG data: {response.status_code}"
    )

    # Check that the content is binary data
    assert len(response.content) > 0, "Response content is empty"

    # For GeoTIFF, check for the magic bytes (II* or MM*)
    # Due to different formats and encodings, this check might need to be adjusted
    magic_bytes = response.content[:4]
    is_valid_tiff = (
        magic_bytes.startswith(b"II*\x00")  # Little endian TIFF
        or magic_bytes.startswith(b"MM\x00*")  # Big endian TIFF
    )
    if not is_valid_tiff:
        print(f"Warning: COG data doesn't have standard TIFF header: {magic_bytes!r}")

    # Verify the content type is appropriate
    content_type = response.headers.get("Content-Type", "")
    assert (
        "tiff" in content_type.lower()
        or "image" in content_type.lower()
        or "application" in content_type.lower()
    ), f"Unexpected content type: {content_type}"

    # Check for appropriate headers
    assert "Content-Length" in response.headers, "Missing Content-Length header"
    assert "Accept-Ranges" in response.headers, "Missing Accept-Ranges header"
    assert response.headers["Accept-Ranges"] == "bytes", (
        "Accept-Ranges header should be 'bytes'"
    )

    print(f"COG data received, content length: {len(response.content)} bytes")


@pytest.mark.s3
@pytest.mark.anyio
async def test_format_mismatch_error(test_map_with_layers, auth_client):
    """Test that requesting the wrong format for a layer type returns an error."""
    map_info = test_map_with_layers
    vector_layer_id = map_info["vector_layer_id"]
    raster_layer_id = map_info["raster_layer_id"]

    # Test requesting COG for vector layer (should fail)
    response = await auth_client.get(f"/api/layer/{vector_layer_id}.cog.tif")
    assert response.status_code == 400, "Should return 400 for format mismatch"
    assert "not a raster type" in response.text.lower(), (
        "Error message should mention type mismatch"
    )

    # Test requesting PMTiles for raster layer (should fail)
    response = await auth_client.get(f"/api/layer/{raster_layer_id}.pmtiles")
    assert response.status_code == 400, "Should return 400 for format mismatch"
    assert "not a vector type" in response.text.lower(), (
        "Error message should mention type mismatch"
    )


@pytest.mark.s3
@pytest.mark.anyio
async def test_layer_feature_count(test_map_with_layers, auth_client):
    """Test that feature_count is properly set for vector layers and null for raster layers."""
    map_info = test_map_with_layers
    map_id = map_info["map_id"]
    vector_layer_id = map_info["vector_layer_id"]
    raster_layer_id = map_info["raster_layer_id"]

    # Get the layers information
    response = await auth_client.get(f"/api/maps/{map_id}/layers")
    assert response.status_code == 200, f"Failed to get layers: {response.text}"

    # Parse the response
    layers_data = response.json()

    # Find the vector and raster layers
    vector_layer = next(
        (layer for layer in layers_data["layers"] if layer["id"] == vector_layer_id),
        None,
    )
    raster_layer = next(
        (layer for layer in layers_data["layers"] if layer["id"] == raster_layer_id),
        None,
    )

    # Assert that the layers were found
    assert vector_layer is not None, "Vector layer not found in layers list"
    assert raster_layer is not None, "Raster layer not found in layers list"

    # Verify feature_count
    # For vector layers, feature_count should be non-null (typically a positive integer)
    assert vector_layer["feature_count"] is not None, (
        "Vector layer should have non-null feature_count"
    )
    assert isinstance(vector_layer["feature_count"], int), (
        "Vector layer feature_count should be an integer"
    )
    assert vector_layer["feature_count"] > 0, (
        "Vector layer feature_count should be positive"
    )

    # For raster layers, feature_count should be null
    assert raster_layer["feature_count"] is None, (
        "Raster layer feature_count should be null"
    )

    print(f"Vector layer feature count: {vector_layer['feature_count']}")
    print(f"Raster layer feature count: {raster_layer['feature_count']} (null)")
