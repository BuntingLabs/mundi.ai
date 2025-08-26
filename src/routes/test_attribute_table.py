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
from pathlib import Path


@pytest.fixture(scope="session")
async def test_map_with_airports_layer(auth_client):
    map_payload = {
        "project": {"layers": [], "crs": {"epsg_code": 3857}},
        "title": "Attribute Table Test Map",
        "description": "Test map for attribute table operations",
    }

    map_response = await auth_client.post("/api/maps/create", json=map_payload)
    assert map_response.status_code == 200, f"Failed to create map: {map_response.text}"
    map_id = map_response.json()["id"]

    file_path = str(
        Path(__file__).parent.parent.parent / "test_fixtures" / "airports.fgb"
    )

    assert os.path.exists(file_path), f"Test file {file_path} must exist for this test"

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


@pytest.fixture(scope="session")
async def test_map_with_counties_layer(auth_client):
    map_payload = {
        "project": {"layers": [], "crs": {"epsg_code": 3857}},
        "title": "Counties Attribute Table Test Map",
        "description": "Test map for attribute table pagination",
    }

    map_response = await auth_client.post("/api/maps/create", json=map_payload)
    assert map_response.status_code == 200, f"Failed to create map: {map_response.text}"
    map_id = map_response.json()["id"]

    file_path = str(
        Path(__file__).parent.parent.parent / "test_fixtures" / "UScounties.gpkg"
    )

    assert os.path.exists(file_path), f"Test file {file_path} must exist for this test"

    with open(file_path, "rb") as f:
        files = {"file": ("UScounties.gpkg", f)}
        data = {"layer_name": "US Counties"}

        layer_response = await auth_client.post(
            f"/api/maps/{map_id}/layers", files=files, data=data
        )

        assert layer_response.status_code == 200, (
            f"Failed to upload layer: {layer_response.text}"
        )
        layer_id = layer_response.json()["id"]

    return {"map_id": map_id, "layer_id": layer_id}


@pytest.mark.anyio
async def test_get_layer_attributes_basic(test_map_with_airports_layer, auth_client):
    layer_id = test_map_with_airports_layer["layer_id"]

    response = await auth_client.get(f"/api/layer/{layer_id}/attributes")

    assert response.status_code == 200, f"Attributes request failed: {response.text}"

    data = response.json()

    assert "data" in data
    assert "offset" in data
    assert "limit" in data
    assert "has_more" in data
    assert "total_count" in data
    assert "field_names" in data

    assert data["offset"] == 0
    assert data["limit"] == 100

    assert isinstance(data["data"], list)
    assert len(data["data"]) == 76, f"Expected 76 airports, got {len(data['data'])}"

    assert data["total_count"] == 76, (
        f"Expected total_count 76, got {data['total_count']}"
    )
    assert data["has_more"] is False

    expected_fields = ["ID", "fk_region", "ELEV", "NAME", "USE"]
    assert data["field_names"] == expected_fields, (
        f"Field names don't match: {data['field_names']}"
    )

    feature = data["data"][0]
    assert "id" in feature
    assert "attributes" in feature
    assert isinstance(feature["attributes"], dict)

    for field_name in expected_fields:
        assert field_name in feature["attributes"], f"Missing field {field_name}"

    first_airport = data["data"][0]
    attrs = first_airport["attributes"]
    assert attrs["ID"] == 76
    assert attrs["fk_region"] == 19
    assert attrs["ELEV"] == 108.0
    assert attrs["NAME"] == "ANNETTE ISLAND"
    assert attrs["USE"] == "Other"


@pytest.mark.anyio
async def test_get_layer_attributes_pagination(
    test_map_with_airports_layer, auth_client
):
    layer_id = test_map_with_airports_layer["layer_id"]

    response1 = await auth_client.get(
        f"/api/layer/{layer_id}/attributes?offset=0&limit=10"
    )
    assert response1.status_code == 200
    data1 = response1.json()

    assert data1["offset"] == 0
    assert data1["limit"] == 10
    assert len(data1["data"]) == 10
    assert data1["has_more"] is True
    assert data1["total_count"] == 76

    assert data1["data"][0]["attributes"]["NAME"] == "ANNETTE ISLAND"

    response2 = await auth_client.get(
        f"/api/layer/{layer_id}/attributes?offset=10&limit=10"
    )
    assert response2.status_code == 200
    data2 = response2.json()

    assert data2["offset"] == 10
    assert data2["limit"] == 10
    assert len(data2["data"]) == 10
    assert data2["has_more"] is True
    assert data2["total_count"] == 76

    first_page_ids = {f["id"] for f in data1["data"]}
    second_page_ids = {f["id"] for f in data2["data"]}
    assert first_page_ids.isdisjoint(second_page_ids), (
        "Pages should contain different features"
    )

    response_last = await auth_client.get(
        f"/api/layer/{layer_id}/attributes?offset=70&limit=10"
    )
    assert response_last.status_code == 200
    data_last = response_last.json()

    assert data_last["offset"] == 70
    assert data_last["limit"] == 10
    assert len(data_last["data"]) == 6
    assert data_last["has_more"] is False
    assert data_last["total_count"] == 76


@pytest.mark.anyio
async def test_get_layer_attributes_large_dataset_pagination(
    test_map_with_counties_layer, auth_client
):
    layer_id = test_map_with_counties_layer["layer_id"]

    response = await auth_client.get(f"/api/layer/{layer_id}/attributes?limit=50")
    assert response.status_code == 200

    data = response.json()
    assert data["limit"] == 50
    assert len(data["data"]) == 50
    assert data["total_count"] == 3221
    assert data["has_more"] is True

    expected_fields = ["STATE_FIPS", "COUNTY_FIP", "FIPS", "STATE", "NAME", "LSAD"]
    assert data["field_names"] == expected_fields

    first_county = data["data"][0]
    attrs = first_county["attributes"]
    assert attrs["STATE_FIPS"] == "23"
    assert attrs["COUNTY_FIP"] == "009"
    assert attrs["FIPS"] == "23009"
    assert attrs["STATE"] == "ME"
    assert attrs["NAME"] == "Hancock"
    assert attrs["LSAD"] == "County"


@pytest.mark.anyio
async def test_get_layer_attributes_validation(
    test_map_with_airports_layer, auth_client
):
    layer_id = test_map_with_airports_layer["layer_id"]

    response = await auth_client.get(f"/api/layer/{layer_id}/attributes?offset=-1")
    assert response.status_code == 400
    assert "Offset must be non-negative" in response.json()["detail"]

    response = await auth_client.get(f"/api/layer/{layer_id}/attributes?limit=0")
    assert response.status_code == 400
    assert "Limit must be between 1 and 100" in response.json()["detail"]

    response = await auth_client.get(f"/api/layer/{layer_id}/attributes?limit=101")
    assert response.status_code == 400
    assert "Limit must be between 1 and 100" in response.json()["detail"]


@pytest.mark.anyio
async def test_get_layer_attributes_nonexistent_layer(auth_client):
    fake_layer_id = "L000000FAKE0"

    response = await auth_client.get(f"/api/layer/{fake_layer_id}/attributes")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_get_layer_attributes_field_types(
    test_map_with_airports_layer, auth_client
):
    layer_id = test_map_with_airports_layer["layer_id"]

    response = await auth_client.get(f"/api/layer/{layer_id}/attributes?limit=1")
    assert response.status_code == 200

    data = response.json()
    feature = data["data"][0]
    attributes = feature["attributes"]

    assert isinstance(attributes["ID"], int), (
        f"ID should be int, got {type(attributes['ID'])}"
    )
    assert isinstance(attributes["fk_region"], int), (
        f"fk_region should be int, got {type(attributes['fk_region'])}"
    )
    assert isinstance(attributes["ELEV"], float), (
        f"ELEV should be float, got {type(attributes['ELEV'])}"
    )
    assert isinstance(attributes["NAME"], str), (
        f"NAME should be str, got {type(attributes['NAME'])}"
    )
    assert isinstance(attributes["USE"], str), (
        f"USE should be str, got {type(attributes['USE'])}"
    )

    assert attributes["ID"] > 0, "ID should be positive"
    assert attributes["fk_region"] > 0, "fk_region should be positive"
    assert attributes["ELEV"] >= 0, "Elevation should be non-negative"
    assert len(attributes["NAME"]) > 0, "Airport name should not be empty"
    assert len(attributes["USE"]) > 0, "Use type should not be empty"


@pytest.mark.anyio
async def test_get_layer_attributes_empty_offset(
    test_map_with_airports_layer, auth_client
):
    layer_id = test_map_with_airports_layer["layer_id"]

    response = await auth_client.get(
        f"/api/layer/{layer_id}/attributes?offset=10000&limit=10"
    )
    assert response.status_code == 200

    data = response.json()
    assert data["offset"] == 10000
    assert data["limit"] == 10
    assert len(data["data"]) == 0
    assert data["has_more"] is False


@pytest.mark.anyio
async def test_get_layer_attributes_no_geometry_in_response(
    test_map_with_airports_layer, auth_client
):
    layer_id = test_map_with_airports_layer["layer_id"]

    response = await auth_client.get(f"/api/layer/{layer_id}/attributes?limit=1")
    assert response.status_code == 200

    data = response.json()

    expected_fields = ["ID", "fk_region", "ELEV", "NAME", "USE"]
    assert data["field_names"] == expected_fields

    geometry_field_names = ["geom", "geometry", "shape", "the_geom", "wkb_geometry"]
    for geom_field in geometry_field_names:
        assert geom_field not in data["field_names"], (
            f"Geometry field {geom_field} should not be in field_names"
        )

    feature = data["data"][0]
    assert set(feature["attributes"].keys()) == set(expected_fields)

    for geom_field in geometry_field_names:
        assert geom_field not in feature["attributes"], (
            f"Geometry field {geom_field} should not be in attributes"
        )


@pytest.mark.anyio
async def test_get_layer_attributes_specific_airports(
    test_map_with_airports_layer, auth_client
):
    layer_id = test_map_with_airports_layer["layer_id"]

    response = await auth_client.get(f"/api/layer/{layer_id}/attributes")
    assert response.status_code == 200

    data = response.json()

    airports_by_name = {f["attributes"]["NAME"]: f["attributes"] for f in data["data"]}

    assert "FAIRBANKS INTL" in airports_by_name
    fairbanks = airports_by_name["FAIRBANKS INTL"]
    assert fairbanks["ID"] == 36
    assert fairbanks["USE"] == "Civilian/Public"
    assert fairbanks["ELEV"] == 396.0

    assert "ANCHORAGE INTL" in airports_by_name
    anchorage = airports_by_name["ANCHORAGE INTL"]
    assert anchorage["ID"] == 49
    assert anchorage["USE"] == "Civilian/Public"
    assert anchorage["ELEV"] == 129.0

    airport_uses = {f["attributes"]["USE"] for f in data["data"]}
    expected_uses = {"Civilian/Public", "Military", "Other", "Joint Military/Civilian"}
    assert expected_uses.issubset(airport_uses), (
        f"Missing expected airport use types. Got: {airport_uses}"
    )
