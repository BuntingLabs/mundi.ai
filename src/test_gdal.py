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

import subprocess
import pytest
from pathlib import Path
from src.test_mbgl_renderer import compare_images

# Reference images directory
REFERENCE_DIR = Path(__file__).parent.parent / "test_fixtures" / "reference_images"
# Test output directory
TEST_OUTPUT_DIR = Path(__file__).parent.parent / "test_output"

# Create directories if they don't exist
REFERENCE_DIR.mkdir(exist_ok=True, parents=True)
TEST_OUTPUT_DIR.mkdir(exist_ok=True, parents=True)


def test_gdalinfo_version():
    """Test that gdalinfo version info can be retrieved."""
    result = subprocess.run(
        ["gdalinfo", "--version"], check=False, capture_output=True, text=True
    )
    if result.returncode != 0:
        pytest.skip(f"gdalinfo command failed: {result.stderr}")
    assert "GDAL" in result.stdout
    assert result.returncode == 0


@pytest.fixture
async def dem_map_with_cog_layer(auth_client):
    """
    Creates a new map and uploads test_fixtures/frazier_8928_75m.dem to it,
    resulting in a layer with a COG URL.
    Yields (map_id, dem_layer_id, project_id).
    """

    # 1. Create an empty map
    response = await auth_client.post(
        "/api/maps/create",
        json={
            "title": "Test Map with DEM COG Layer",
        },
    )
    response.raise_for_status()
    map_data = response.json()
    map_id = map_data["id"]
    project_id = map_data["project_id"]

    # 2. Upload the DEM file to this map
    # Assumes test_gdal.py is in src/ and test_fixtures/ is at the project root.
    dem_file_path = (
        Path(__file__).parent.parent / "test_fixtures" / "frazier_8928_75m.dem"
    )

    if not dem_file_path.exists():
        pytest.skip(f"DEM file not found: {dem_file_path}")

    with open(dem_file_path, "rb") as f:
        files = {"file": (dem_file_path.name, f, "application/octet-stream")}
        # The endpoint expects form data for layer_name and add_layer_to_map
        data = {"layer_name": dem_file_path.stem, "add_layer_to_map": True}
        # Correct endpoint URL based on postgres_routes.py @upload_layer definition
        upload_response = await auth_client.post(
            f"/api/maps/{map_id}/layers",
            files=files,
            data=data,
        )

    upload_response.raise_for_status()
    layer_data = upload_response.json()

    # Assuming the upload response contains the new layer's ID,
    # which is used in the COG URL.
    dem_layer_id = layer_data["id"]
    # Get the child map ID from the DAG response
    child_map_id = layer_data["dag_child_map_id"]

    yield child_map_id, dem_layer_id, project_id

    # Consider adding cleanup (e.g., delete map) if necessary for the test environment.


@pytest.mark.anyio
async def test_dem_layer_has_correct_cog_url(dem_map_with_cog_layer, auth_client):
    """
    Tests that a DEM layer, added to a map via file upload,
    has the correct cog:// URL format including styling parameters.
    """
    map_id, dem_layer_id, _ = dem_map_with_cog_layer
    # 1. Verify the layer ID exists in the map details
    response = await auth_client.get(f"/api/maps/{map_id}")
    response.raise_for_status()
    map_details = response.json()
    assert "layers" in map_details, "Map details JSON should contain 'layers' field"

    project_layers = map_details["layers"]
    layer_found_in_map = any(layer["id"] == dem_layer_id for layer in project_layers)
    assert layer_found_in_map, (
        f"DEM layer with ID '{dem_layer_id}' not found in map {map_id}. Layers: {project_layers}"
    )

    # 2. Request the style.json and verify the COG source URL
    style_response = await auth_client.get(f"/api/maps/{map_id}/style.json")
    style_response.raise_for_status()
    style_json = style_response.json()

    assert "sources" in style_json, "Style JSON should contain 'sources' field"
    sources = style_json["sources"]

    cog_source_info = None
    expected_url_path_segment = f"/api/layer/{dem_layer_id}.cog.tif"
    expected_cog_url_base = f"cog://{expected_url_path_segment}"

    for source_name, source_details in sources.items():
        if source_details.get("type") == "raster" and "url" in source_details:
            if source_details["url"].startswith(expected_cog_url_base):
                cog_source_info = source_details
                break

    assert cog_source_info is not None, (
        f"COG source with base URL '{expected_cog_url_base}' not found in style.json sources for map {map_id}. Sources: {sources}"
    )

    cog_url = cog_source_info["url"]

    # Verify the cog:// URL structure and styling fragment
    assert cog_url.startswith(expected_cog_url_base), (
        f"COG source URL base does not match.\nGot:      {cog_url}\nExpected base: {expected_cog_url_base}"
    )
    # Check for a default styling fragment (adjust if defaults change)
    expected_styling_fragment = "#color:BrewerSpectral9,963.0,2443.0,c"
    assert expected_styling_fragment in cog_url, (
        f"COG source URL does not contain expected styling fragment '{expected_styling_fragment}'.\nGot: {cog_url}"
    )

    # 3. Test that the .cog.tif endpoint itself is accessible and returns OK
    cog_tif_path = expected_url_path_segment  # e.g., /api/layer/{id}.cog.tif
    cog_response = await auth_client.get(cog_tif_path)

    assert cog_response.status_code == 200, (
        f"Expected 200 OK from COG endpoint {cog_tif_path}, but got {cog_response.status_code}. Response: {cog_response.text}"
    )


@pytest.mark.anyio
async def test_dem_map_social_preview(dem_map_with_cog_layer, auth_client):
    """Test getting a social media preview image for a DEM map."""
    map_id, dem_layer_id, project_id = dem_map_with_cog_layer

    # First request should return a placeholder JPEG
    response = await auth_client.get(f"/api/projects/{project_id}/social.webp")

    # Verify initial response
    assert response.status_code == 200
    assert response.headers.get("Content-Type") == "image/webp"
    assert len(response.content) > 0, "Response content is empty"

    # Second request should return the actual WebP image
    response = await auth_client.get(f"/api/projects/{project_id}/social.webp")

    # Verify response
    assert response.status_code == 200
    assert response.headers.get("Content-Type") == "image/webp"
    assert len(response.content) > 0, "Response content is empty"

    # Save the image for inspection
    output_path = TEST_OUTPUT_DIR / "rastersocial.webp"
    with open(output_path, "wb") as f:
        f.write(response.content)

    print(f"DEM map social preview image saved to: {output_path}")

    # Compare with reference image
    reference_image_path = REFERENCE_DIR / "rastersocial.webp"
    assert reference_image_path.exists(), (
        f"Reference image not found at {reference_image_path}"
    )

    # Compare with reference image using the same function as in test_mbgl_renderer
    is_similar, diff_value = compare_images(
        output_path, reference_image_path, threshold=0.001
    )

    print(f"Image difference: {diff_value:.6f} (threshold: 0.001)")
    assert is_similar, f"Rendered image differs from reference (diff: {diff_value:.6f})"


@pytest.mark.anyio
async def test_describe_dem_layer(dem_map_with_cog_layer, auth_client):
    """Test the layer description endpoint with a DEM layer."""
    # Get the layer ID from the fixture
    _, dem_layer_id, _ = dem_map_with_cog_layer

    # Call the describe endpoint
    response = await auth_client.get(f"/api/layer/{dem_layer_id}/describe")

    # Check that the response is successful
    assert response.status_code == 200, (
        f"Failed to get layer description: {response.text}"
    )

    # Verify the content type
    assert "text/plain" in response.headers["content-type"]

    # Check for key sections in the markdown output
    content = response.text
    assert "# Layer: frazier_8928_75m" in content
    assert "## Geographic Extent" in content
    assert "## Raster Statistics" in content

    # Verify specific data points
    assert f"ID: {dem_layer_id}" in content
    assert "Type: raster" in content
    assert "Bounds (WGS84): -119.000768,34.747827,-118.875899,34.877212" in content
    assert "Min Value: 963.0" in content
    assert "Max Value: 2443.0" in content

    # Write the response to a file for inspection
    output_path = TEST_OUTPUT_DIR / "dem_layer_description.md"
    with open(output_path, "w") as f:
        f.write(content)

    print(f"DEM layer description saved to: {output_path}")
