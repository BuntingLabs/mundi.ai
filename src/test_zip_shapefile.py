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

import os
import tempfile
import zipfile
import pytest


@pytest.mark.s3
@pytest.mark.anyio
async def test_zip_shapefile_upload(auth_client):
    # Create a temporary map for testing
    project = {}

    payload = {
        "project": project,
        "title": "Zip Shapefile Test Map",
        "description": "Test map for ZIP shapefile upload",
    }

    response = await auth_client.post(
        "/api/maps/create",
        json=payload,
    )

    assert response.status_code == 200, (
        f"Map creation failed: {response.status_code}, {response.text}"
    )
    map_id = response.json()["id"]

    temp_zip_path: str | None = None
    try:
        temp_zip_path = tempfile.mktemp(suffix=".zip")
        shp_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "test_fixtures/Public_Land_Survey_Town_Range",
        )

        assert os.path.exists(shp_dir), f"Shapefile directory not found: {shp_dir}"

        with zipfile.ZipFile(temp_zip_path, "w") as zipf:
            for filename in os.listdir(shp_dir):
                file_path = os.path.join(shp_dir, filename)
                if os.path.isfile(file_path):
                    zipf.write(file_path, filename)

        with open(temp_zip_path, "rb") as zip_file:
            files = {"file": ("town_range.zip", zip_file, "application/zip")}
            response = await auth_client.post(
                f"/api/maps/{map_id}/layers",
                files=files,
                data={"layer_name": "Town Range"},
            )

            assert response.status_code == 200
            result = response.json()

            assert result["id"] is not None
            assert result["name"] == "Town Range"
            assert result["type"] == "vector"

            layer_id = result["id"]
            response = await auth_client.get(
                f"/api/layer/{layer_id}.geojson",
            )

            assert response.status_code == 200
            assert response.headers["Content-Type"] == "application/geo+json"

            geojson = response.json()
            assert "features" in geojson
            assert len(geojson["features"]) == 2975

            feature = geojson["features"][0]
            assert "geometry" in feature
            assert "properties" in feature

            assert "CNTY_NAME" in feature["properties"]
            assert "CNTY_NUM" in feature["properties"]
            assert "COMMENT" in feature["properties"]

    finally:
        if temp_zip_path is not None and os.path.exists(temp_zip_path):
            os.unlink(temp_zip_path)


@pytest.mark.anyio
async def test_zip_shapefile_upload_macosx(auth_client):
    project = {}

    payload = {
        "project": project,
        "title": "Zip Shapefile Test Map Mac OSX",
        "description": "Test map for ZIP shapefile upload",
    }

    response = await auth_client.post(
        "/api/maps/create",
        json=payload,
    )

    assert response.status_code == 200, (
        f"Map creation failed: {response.status_code}, {response.text}"
    )
    map_id = response.json()["id"]

    temp_zip_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "test_fixtures/withmacosx.zip",
    )

    assert os.path.exists(temp_zip_path), f"Test fixture not found: {temp_zip_path}"

    with open(temp_zip_path, "rb") as zip_file:
        files = {"file": ("withmacosx.zip", zip_file, "application/zip")}
        response = await auth_client.post(
            f"/api/maps/{map_id}/layers",
            files=files,
            data={"layer_name": "Town Range"},
        )

        assert response.status_code == 200
        result = response.json()

        assert result["id"] is not None
        assert result["name"] == "Town Range"
        assert result["type"] == "vector"

        layer_id = result["id"]
        response = await auth_client.get(
            f"/api/layer/{layer_id}.geojson",
        )

        assert response.status_code == 200
        assert response.headers["Content-Type"] == "application/geo+json"

        geojson = response.json()
        assert "features" in geojson
        assert len(geojson["features"]) == 2975

        feature = geojson["features"][0]
        assert "geometry" in feature
        assert "properties" in feature

        assert "CNTY_NAME" in feature["properties"]
        assert "CNTY_NUM" in feature["properties"]
        assert "COMMENT" in feature["properties"]


@pytest.mark.s3
@pytest.mark.anyio
async def test_invalid_zip_file_upload(auth_client):
    # Create a temporary map for testing
    project = {}

    payload = {
        "project": project,
        "title": "Invalid Zip Test Map",
        "description": "Test map for invalid ZIP file upload",
    }

    response = await auth_client.post(
        "/api/maps/create",
        json=payload,
    )

    assert response.status_code == 200, (
        f"Map creation failed: {response.status_code}, {response.text}"
    )
    map_id = response.json()["id"]

    temp_zip_path: str | None = None
    try:
        temp_zip_path = tempfile.mktemp(suffix=".zip")

        with zipfile.ZipFile(temp_zip_path, "w") as zipf:
            zipf.writestr("test.txt", "This is a test file with no shapefiles")

        with open(temp_zip_path, "rb") as zip_file:
            files = {"file": ("invalid.zip", zip_file, "application/zip")}
            response = await auth_client.post(
                f"/api/maps/{map_id}/layers",
                files=files,
                data={"layer_name": "Invalid ZIP"},
            )

            assert response.status_code == 400

    finally:
        if temp_zip_path is not None and os.path.exists(temp_zip_path):
            os.unlink(temp_zip_path)
