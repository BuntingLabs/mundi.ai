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
from pathlib import Path


@pytest.fixture
async def test_map_with_layer(auth_client):
    map_response = await auth_client.post(
        "/api/maps/create",
        json={
            "title": "Set Layer Style Test Map",
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

        return {
            "map_id": map_id,
            "child_map_id": child_map_id,
            "layer_id": layer_id,
        }


@pytest.mark.anyio
async def test_set_layer_style_success(auth_client, test_map_with_layer):
    layer_id = test_map_with_layer["layer_id"]
    map_id = test_map_with_layer["child_map_id"]

    style_request = {
        "maplibre_json_layers": [
            {
                "id": f"{layer_id}-fill",
                "type": "fill",
                "source": layer_id,
                "paint": {
                    "fill-color": "#FF6B6B",
                    "fill-opacity": 0.69,
                    "fill-outline-color": "#000000",
                },
            }
        ],
        "map_id": map_id,
    }

    style_response = await auth_client.post(
        f"/api/layers/{layer_id}/style", json=style_request
    )

    assert style_response.status_code == 200, (
        f"Failed to set style: {style_response.text}"
    )
    style_data = style_response.json()
    assert "style_id" in style_data
    assert style_data["layer_id"] == layer_id

    map_style_response = await auth_client.get(f"/api/maps/{map_id}/style.json")
    assert map_style_response.status_code == 200, (
        f"Failed to get style.json: {map_style_response.text}"
    )

    style_json = map_style_response.json()

    found_layer = None
    for layer in style_json.get("layers", []):
        if layer.get("id") == f"{layer_id}-fill":
            found_layer = layer
            break

    assert found_layer is not None, f"Layer {layer_id} not found in style.json"
    assert found_layer["type"] == "fill"
    assert found_layer["source"] == layer_id
    assert found_layer["source-layer"] == "reprojectedfgb"
    assert found_layer["paint"]["fill-color"] == "#FF6B6B"
    assert found_layer["paint"]["fill-opacity"] == 0.69


@pytest.mark.anyio
async def test_set_layer_style_invalid_source(auth_client, test_map_with_layer):
    layer_id = test_map_with_layer["layer_id"]
    map_id = test_map_with_layer["child_map_id"]

    style_request = {
        "maplibre_json_layers": [
            {
                "id": f"{layer_id}",
                "type": "fill",
                "source": "Lwrongsource",
                "paint": {"fill-color": "#FF6B6B", "fill-opacity": 0.7},
            }
        ],
        "map_id": map_id,
    }

    style_response = await auth_client.post(
        f"/api/layers/{layer_id}/style", json=style_request
    )

    assert style_response.status_code == 400
    error_detail = style_response.json()["detail"]
    assert "Layer source must be" in error_detail
    assert layer_id in error_detail


@pytest.mark.anyio
async def test_set_layer_style_invalid_layers_type(auth_client, test_map_with_layer):
    layer_id = test_map_with_layer["layer_id"]
    map_id = test_map_with_layer["child_map_id"]

    style_request = {"maplibre_json_layers": "not_an_array", "map_id": map_id}

    style_response = await auth_client.post(
        f"/api/layers/{layer_id}/style", json=style_request
    )

    assert style_response.status_code == 422
    error_detail = style_response.json()["detail"]
    assert len(error_detail) > 0
