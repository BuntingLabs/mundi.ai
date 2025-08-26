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
import json
import os
from pathlib import Path
import numpy as np
from PIL import Image
import secrets
import uuid

from src.structures import get_async_db_connection

# Reference images directory
REFERENCE_DIR = Path(__file__).parent.parent / "test_fixtures" / "reference_images"
# Test output directory
TEST_OUTPUT_DIR = Path(__file__).parent.parent / "test_output"

# Create directories if they don't exist
REFERENCE_DIR.mkdir(exist_ok=True, parents=True)
TEST_OUTPUT_DIR.mkdir(exist_ok=True, parents=True)


def compare_images(actual_image_path, reference_image_path, threshold=0.001):
    """Compare two images and return True if they are similar enough.

    Args:
        actual_image_path: Path to the actual rendered image
        reference_image_path: Path to the reference image
        threshold: Maximum allowed difference (0-1 range, where 0 means identical)

    Returns:
        bool: True if images are similar enough, False otherwise
        float: The actual difference value
    """
    # Load images
    actual_img = np.array(Image.open(actual_image_path).convert("RGB"))
    reference_img = np.array(Image.open(reference_image_path).convert("RGB"))

    # Ensure images are the same size
    if actual_img.shape != reference_img.shape:
        raise ValueError(
            f"Images have different shapes: {actual_img.shape} != {reference_img.shape}"
        )

    # Calculate mean squared error
    mse = np.mean((actual_img - reference_img) ** 2)
    max_possible_mse = 255**2

    # Normalize to 0-1 range
    diff = mse / max_possible_mse

    return diff <= threshold, diff


@pytest.fixture
async def test_map_with_osm_layer(auth_client):
    map_payload = {
        "title": "MapLibre GL Test Map",
        "description": "Test map for MapLibre GL rendering",
    }
    map_response = await auth_client.post("/api/maps/create", json=map_payload)
    assert map_response.status_code == 200, f"Failed to create map: {map_response.text}"
    map_id = map_response.json()["id"]
    return {"map_id": map_id}


@pytest.fixture
async def test_map_with_idaho_layer(auth_client):
    map_payload = {
        "title": "Idaho Test Map",
        "description": "Test map with Idaho layer for style testing",
    }
    map_response = await auth_client.post("/api/maps/create", json=map_payload)
    assert map_response.status_code == 200, f"Failed to create map: {map_response.text}"
    current_map_id = map_response.json()["id"]

    file_path = str(
        Path(__file__).parent.parent / "test_fixtures" / "idaho_weatherstations.geojson"
    )
    if not os.path.exists(file_path):
        pytest.skip(f"Test file {file_path} not found")

    with open(file_path, "rb") as f:
        layer_response = await auth_client.post(
            f"/api/maps/{current_map_id}/layers",
            files={
                "file": ("idaho_weatherstations.geojson", f, "application/octet-stream")
            },
            data={"layer_name": "Idaho Weather Stations"},
        )
        assert layer_response.status_code == 200, (
            f"Failed to upload layer: {layer_response.text}"
        )
        response_data = layer_response.json()
        layer_id = response_data["id"]
        child_map_id = response_data["dag_child_map_id"]

    return {
        "map_id": child_map_id,
        "layer_id": layer_id,
    }


@pytest.mark.anyio
async def test_mbgl_renderer(test_map_with_osm_layer, auth_client):
    # Get the map ID from the fixture
    map_id = test_map_with_osm_layer["map_id"]

    # British Isles and Ireland bounding box (wider view)
    british_isles_bbox = {
        "xmin": -12.0,  # Western Ireland
        "ymin": 49.0,  # Southern England
        "xmax": 2.5,  # Eastern England
        "ymax": 60.0,  # Northern Scotland
    }

    # Render settings
    width = 1200
    height = 900

    # Format the bbox as a comma-separated string as expected by the render.png endpoint
    bbox_str = f"{british_isles_bbox['xmin']},{british_isles_bbox['ymin']},{british_isles_bbox['xmax']},{british_isles_bbox['ymax']}"

    # Make request to render using mbgl renderer
    url = f"/api/maps/{map_id}/render.png?width={width}&height={height}&renderer=mbgl"
    url += f"&bbox={bbox_str}"

    # Log the request for traceability
    print(f"Rendering British Isles with mbgl-renderer using URL: {url}")

    response = await auth_client.get(url)

    # Assert response is successful
    assert response.status_code == 200, f"MapLibre GL rendering failed: {response.text}"
    assert response.headers["Content-Type"] == "image/png"
    assert len(response.content) > 0, "Response content is empty"

    # Define paths for current and reference images
    current_image_path = TEST_OUTPUT_DIR / "british_isles_maplibre_current.png"
    reference_image_path = REFERENCE_DIR / "british_isles_maplibre.png"

    # Save the current rendered image
    with open(current_image_path, "wb") as f:
        f.write(response.content)

    print(f"Rendered MapLibre GL output saved to: {current_image_path}")

    # Verify the reference image exists
    assert reference_image_path.exists(), (
        f"Reference image not found at {reference_image_path}"
    )

    # Compare with reference image
    is_similar, diff_value = compare_images(
        current_image_path, reference_image_path, threshold=0.003
    )

    # Show detailed comparison info
    print(f"Image difference: {diff_value:.6f} (threshold: 0.003)")

    if not is_similar:
        # Output warning if images differ significantly
        print("WARNING: Images differ significantly!")
        print(f"Current image: {current_image_path}")
        print(f"Reference image: {reference_image_path}")

    # Assert that the images are similar enough
    assert is_similar, f"Rendered image differs from reference (diff: {diff_value:.6f})"


@pytest.mark.anyio
async def test_mbgl_barcelona(test_map_with_vector_layers, auth_client):
    map_id = test_map_with_vector_layers["map_id"]
    barcelona_bbox = {"xmin": 2.05, "ymin": 41.30, "xmax": 2.25, "ymax": 41.45}
    width = 1200
    height = 900
    bbox_str = f"{barcelona_bbox['xmin']},{barcelona_bbox['ymin']},{barcelona_bbox['xmax']},{barcelona_bbox['ymax']}"
    url = f"/api/maps/{map_id}/render.png?width={width}&height={height}&renderer=mbgl&bbox={bbox_str}"
    response = await auth_client.get(url)
    assert response.status_code == 200, f"MapLibre GL rendering failed: {response.text}"
    assert response.headers["Content-Type"] == "image/png"
    assert len(response.content) > 0, "Response content is empty"
    current_image_path = TEST_OUTPUT_DIR / "barcelona.png"
    with open(current_image_path, "wb") as f:
        f.write(response.content)
    reference_image_path = REFERENCE_DIR / "barcelona.png"
    is_similar, diff_value = compare_images(
        current_image_path, reference_image_path, threshold=0.003
    )
    print(f"Image difference: {diff_value:.6f} (threshold: 0.003)")
    assert is_similar, f"Rendered image differs from reference (diff: {diff_value:.6f})"


@pytest.mark.anyio
async def test_mbgl_idaho(test_map_with_idaho_layer, auth_client):
    map_id = test_map_with_idaho_layer["map_id"]
    layer_id = test_map_with_idaho_layer["layer_id"]
    maplibre_style = [
        {
            "id": "station_circles",
            "type": "circle",
            "source": layer_id,
            "source-layer": "reprojectedfgb",
            "paint": {
                "circle-radius": [
                    "interpolate",
                    ["linear"],
                    ["get", "ELEVATION"],
                    2000,
                    4,
                    8000,
                    10,
                ],
                "circle-color": [
                    "interpolate",
                    ["linear"],
                    ["get", "ELEVATION"],
                    2000,
                    "#fee8c8",
                    5000,
                    "#fdbb84",
                    8000,
                    "#e34a33",
                ],
                "circle-opacity": 0.8,
                "circle-stroke-color": "#000000",
                "circle-stroke-width": 0.5,
            },
        }
    ]

    def generate_style_id():
        valid_chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return "S" + "".join(secrets.choice(valid_chars) for _ in range(11))

    async with get_async_db_connection() as conn:
        style_result = await conn.fetchrow(
            """
            INSERT INTO layer_styles (style_id, layer_id, style_json, created_by)
            VALUES (
                $1, $2, $3, $4
            )
            RETURNING style_id
            """,
            generate_style_id(),
            layer_id,
            json.dumps(maplibre_style),
            str(uuid.uuid4()),
        )
        new_style_id = style_result[0]
        await conn.execute(
            """
            INSERT INTO map_layer_styles (map_id, layer_id, style_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (map_id, layer_id) DO UPDATE SET style_id = EXCLUDED.style_id
            """,
            map_id,
            layer_id,
            new_style_id,
        )

    idaho_bbox = {"xmin": -117.2, "ymin": 41.9, "xmax": -111.0, "ymax": 49.0}
    width = 768
    height = 768
    bbox_str = f"{idaho_bbox['xmin']},{idaho_bbox['ymin']},{idaho_bbox['xmax']},{idaho_bbox['ymax']}"
    url = f"/api/maps/{map_id}/render.png?width={width}&height={height}&renderer=mbgl&bbox={bbox_str}"
    response = await auth_client.get(url)
    assert response.status_code == 200, f"MapLibre GL rendering failed: {response.text}"
    assert response.headers["Content-Type"] == "image/png"
    assert len(response.content) > 0, "Response content is empty"
    current_image_path = TEST_OUTPUT_DIR / "idaho_current.png"
    reference_image_path = REFERENCE_DIR / "idaho_current.png"
    with open(current_image_path, "wb") as f:
        f.write(response.content)
    print(f"Rendered Idaho map saved to: {current_image_path}")
    assert reference_image_path.exists(), (
        f"Reference image not found at {reference_image_path}"
    )
    is_similar, diff_value = compare_images(
        current_image_path, reference_image_path, threshold=0.003
    )
    print(f"Image difference: {diff_value:.6f} (threshold: 0.003)")
    assert is_similar, (
        f"Rendered image does not match reference (diff: {diff_value:.6f})"
    )
