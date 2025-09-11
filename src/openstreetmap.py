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
import asyncio
import aiohttp
from pathlib import Path
from typing import List
from fastapi import UploadFile
from io import BytesIO
from src.dependencies.session import UserContext
from src.routes.postgres_routes import (
    internal_upload_layer,
    InternalLayerUploadResponse,
)
from src.structures import async_conn


async def download_from_openstreetmap(
    map_id: str,
    bbox: List[float],
    tags: str,
    new_layer_name: str,
    session: UserContext,
):
    api_key = os.environ.get("BUNTINGLABS_OSM_API_KEY")
    if not api_key:
        raise Exception("OpenStreetMap API key not configured")

    # Format bbox for OSM API
    bbox_str = "%f,%f,%f,%f" % tuple(bbox)
    # Stream OSM data directly to memory
    osm_url = f"https://osm.buntinglabs.com/v1/osm/extract?tags={tags}&api_key={api_key}&bbox={bbox_str}"
    async with aiohttp.ClientSession() as client_session:
        async with client_session.get(osm_url, timeout=30) as response:
            if response.status != 200:
                raise Exception(
                    f"OSM API request failed with status {response.status}, {(await response.text())[:100]}"
                )
            geojson_data = await response.read()

    # Get project_id from map_id
    user_id = session.get_user_id()
    async with async_conn("get_project_id_for_osm") as conn:
        map_row = await conn.fetchrow(
            """
            SELECT project_id
            FROM user_mundiai_maps
            WHERE id = $1 AND owner_uuid = $2 AND soft_deleted_at IS NULL
            """,
            map_id,
            user_id,
        )
        if not map_row:
            raise Exception(f"Map {map_id} not found")
        project_id: str = map_row["project_id"]

    with tempfile.TemporaryDirectory() as temp_dir:
        # Save GeoJSON to temporary file
        geojson_path = Path(temp_dir) / "osm.geojson"
        with open(geojson_path, "wb") as f:
            f.write(geojson_data)

        # Define geometry types to filter
        geometry_types = [
            {
                "name": "points",
                "filter": "OGR_GEOMETRY='POINT' OR OGR_GEOMETRY='MULTIPOINT'",
            },
            {
                "name": "lines",
                "filter": "OGR_GEOMETRY='LINESTRING' OR OGR_GEOMETRY='MULTILINESTRING'",
            },
            {
                "name": "polygons",
                "filter": "OGR_GEOMETRY='POLYGON' OR OGR_GEOMETRY='MULTIPOLYGON'",
            },
        ]

        uploaded_layers = []
        # Process each geometry type
        for geom in geometry_types:
            gpkg_path = Path(temp_dir) / f"osm_{geom['name']}.gpkg"

            # Filter by geometry type using async subprocess
            proc = await asyncio.create_subprocess_exec(
                "ogr2ogr",
                "-f",
                "GPKG",
                str(gpkg_path),
                str(geojson_path),
                "-where",
                geom["filter"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            # Check if the GPKG file exists and has features
            if gpkg_path.exists() and gpkg_path.stat().st_size > 0:
                try:
                    # Get feature count using async subprocess
                    proc = await asyncio.create_subprocess_exec(
                        "ogrinfo",
                        "-so",
                        str(gpkg_path),
                        "osm",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await proc.communicate()
                    feature_count_output = stdout.decode("utf-8")

                    if "Feature Count" in feature_count_output:
                        feature_count = int(
                            feature_count_output.split("Feature Count:")[1]
                            .split("\n")[0]
                            .strip()
                        )
                    else:
                        feature_count = 0
                except Exception:
                    # If ogrinfo fails, assume no features
                    feature_count = 0

                # Upload layer if it has features
                if feature_count > 0:
                    with open(gpkg_path, "rb") as f:
                        upload_file = UploadFile(
                            filename=f"osm_{geom['name']}.gpkg", file=BytesIO(f.read())
                        )

                    layer_response: InternalLayerUploadResponse = (
                        await internal_upload_layer(
                            map_id=map_id,
                            file=upload_file,
                            layer_name=f"{new_layer_name}_{geom['name']}",
                            add_layer_to_map=False,
                            user_id=user_id,
                            project_id=project_id,
                        )
                    )

                    uploaded_layers.append(
                        {
                            "layer_id": layer_response.id,
                            "geometry_type": geom["name"],
                            "feature_count": feature_count,
                        }
                    )

    # Return the layer IDs and status
    return {
        "status": "success",
        "uploaded_layers": uploaded_layers,
        "message": f"Successfully downloaded OSM data ({tags}) and created {len(uploaded_layers)} layers",
    }


def has_openstreetmap_api_key():
    """Check if OpenStreetMap API key is configured"""
    api_key = os.environ.get("BUNTINGLABS_OSM_API_KEY")
    return api_key is not None and api_key.strip() != ""
