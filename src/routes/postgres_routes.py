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
import uuid
import math
import secrets
import json
import csv
from io import StringIO
from fastapi import (
    APIRouter,
    HTTPException,
    status,
    Request,
    Depends,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field
from src.dependencies.dag import forked_map_by_user
from src.database.models import MundiMap, MapLayer
from ..dependencies.session import (
    verify_session_required,
    verify_session_optional,
    UserContext,
)
from typing import List, Optional
import logging
from datetime import datetime
from pyproj import Transformer
from osgeo import osr
from fastapi import File, UploadFile, Form
from redis import Redis
import tempfile
from starlette.responses import (
    JSONResponse as StarletteJSONResponse,
)
import asyncio
from boto3.s3.transfer import TransferConfig
from src.utils import (
    get_bucket_name,
    process_zip_with_shapefile,
    get_async_s3_client,
    process_kmz_to_kml,
)
from osgeo import gdal
import subprocess
import ipaddress
import socket
from urllib.parse import urlparse
from src.symbology.llm import generate_maplibre_layers_for_layer_id
from src.routes.layer_router import describe_layer_internal
from ..structures import get_async_db_connection, async_conn
from ..dependencies.base_map import BaseMapProvider, get_base_map_provider
from ..dependencies.postgis import get_postgis_provider
from ..dependencies.layer_describer import LayerDescriber, get_layer_describer
from ..dependencies.postgres_connection import (
    PostgresConnectionManager,
    get_postgres_connection_manager,
)
from typing import Callable
from opentelemetry import trace
from src.dag import DAGEditOperationResponse
from src.dependencies.dag import get_map, get_layer

import fiona

fiona.drvsupport.supported_drivers["WFS"] = "r"


logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

redis = Redis(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    decode_responses=True,
)


def validate_remote_url(url: str, source_type: str) -> str:
    """
    Validate remote URL to prevent SSRF attacks and ensure proper format.

    Args:
        url: The URL to validate
        source_type: Type of source ('vector', 'raster', 'sheets')

    Returns:
        The validated and possibly modified URL

    Raises:
        HTTPException: If URL is invalid or potentially malicious
    """
    # Basic URL format validation
    if source_type == "sheets":
        # CSV sources must have the CSV:/vsicurl/ prefix
        if not url.startswith("CSV:/vsicurl/"):
            raise HTTPException(
                status_code=400,
                detail="Google Sheets URLs must use CSV:/vsicurl/https://... format",
            )
        # Extract the actual URL from CSV:/vsicurl/URL format
        actual_url = url.replace("CSV:/vsicurl/", "")
    else:
        actual_url = url

    # URL must start with http:// or https://
    if not (actual_url.startswith("http://") or actual_url.startswith("https://")):
        raise HTTPException(
            status_code=400, detail="URL must start with http:// or https://"
        )

    try:
        parsed = urlparse(actual_url)
        hostname = parsed.hostname

        if not hostname:
            raise HTTPException(status_code=400, detail="Invalid URL: missing hostname")

        # Resolve hostname to IP address to check for private ranges
        try:
            # Get all IP addresses for the hostname
            addr_info = socket.getaddrinfo(
                hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
            )
            ips = [info[4][0] for info in addr_info]

            for ip_str in ips:
                try:
                    ip = ipaddress.ip_address(ip_str)

                    # Block private IP ranges
                    if ip.is_private:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Access to private IP addresses is not allowed: {ip_str}",
                        )

                    # Block loopback
                    if ip.is_loopback:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Access to loopback addresses is not allowed: {ip_str}",
                        )

                    # Block link-local addresses
                    if ip.is_link_local:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Access to link-local addresses is not allowed: {ip_str}",
                        )

                    # Block multicast
                    if ip.is_multicast:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Access to multicast addresses is not allowed: {ip_str}",
                        )

                    # Block cloud metadata endpoints specifically
                    cloud_metadata_ips = [
                        "169.254.169.254",  # AWS, GCP, Azure metadata
                        "169.254.170.2",  # ECS task metadata
                        "100.100.100.200",  # Alibaba Cloud metadata
                    ]

                    if ip_str in cloud_metadata_ips:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Access to cloud metadata endpoints is not allowed: {ip_str}",
                        )

                except ValueError:
                    # Don't skip invalid IP addresses - reject them
                    raise HTTPException(
                        status_code=400, detail=f"Invalid IP address format: {ip_str}"
                    )

        except socket.gaierror:
            raise HTTPException(
                status_code=400, detail=f"Cannot resolve hostname: {hostname}"
            )

    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=400, detail=f"Invalid URL format: {str(e)}")

    return url


# Create router
router = APIRouter()

# Create separate router for basemap endpoints
basemap_router = APIRouter()

one_shot_config = TransferConfig(multipart_threshold=5 * 1024**3)  # 5 GiB


def generate_id(length=12, prefix=""):
    """Generate a unique ID for the map or layer.

    Using characters [1-9A-HJ-NP-Za-km-z] (excluding 0, O, I, l)
    to avoid ambiguity in IDs.
    """
    assert len(prefix) in [0, 1], "Prefix must be at most 1 character"

    valid_chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    result = "".join(secrets.choice(valid_chars) for _ in range(length - len(prefix)))
    return prefix + result


class MapCreateRequest(BaseModel):
    title: str = Field(
        default="Untitled Map", description="Display name for the new map"
    )
    description: str = Field(
        default="", description="Optional description of the map's purpose or contents"
    )


class MapResponse(BaseModel):
    id: str = Field(description="Unique identifier for the map")
    project_id: str = Field(
        description="ID of the project containing this map. Projects can contain multiple related maps."
    )
    title: str = Field(description="Display name of the map")
    description: str = Field(
        description="Optional description of the map's purpose or contents"
    )
    created_on: str = Field(description="ISO timestamp when the map was created")
    last_edited: str = Field(description="ISO timestamp when the map was last modified")


class UserMapsResponse(BaseModel):
    maps: List[MapResponse]


class LayerResponse(BaseModel):
    id: str
    name: str
    type: str
    metadata: Optional[dict] = None
    bounds: Optional[List[float]] = (
        None  # [xmin, ymin, xmax, ymax] in WGS84 coordinates
    )
    geometry_type: Optional[str] = None  # point, multipoint, line, polygon, etc.
    feature_count: Optional[int] = None  # number of features in the layer
    original_srid: Optional[int] = None  # original projection EPSG code


class LayersListResponse(BaseModel):
    map_id: str
    layers: List[LayerResponse]


class LayerUploadResponse(DAGEditOperationResponse):
    id: str = Field(description="Unique identifier for the newly uploaded layer")
    name: str = Field(description="Display name of the layer as it appears in the map")
    type: str = Field(description="Layer type (vector, raster, or point_cloud)")
    url: str = Field(
        description="Direct URL to access the layer data (PMTiles for vector, COG for raster)"
    )
    message: str = Field(
        default="Layer added successfully",
        description="Status message confirming successful upload",
    )


class RemoteLayerRequest(BaseModel):
    url: str = Field(description="Remote URL to the spatial data file")
    name: str = Field(description="Display name for the layer")
    source_type: str = Field(
        description="Type of remote source: 'vector', 'raster', 'sheets'"
    )
    add_layer_to_map: bool = Field(
        default=True, description="Whether to add layer to the map"
    )


class InternalLayerUploadResponse(BaseModel):
    id: str
    name: str
    type: str
    url: str  # Direct URL to the layer
    message: str = "Layer added successfully"


class LayerRemovalResponse(DAGEditOperationResponse):
    layer_id: str
    layer_name: str
    message: str = "Layer successfully removed from map"


class PresignedUrlResponse(BaseModel):
    url: str
    expires_in_seconds: int = 3600 * 24  # Default 24 hours
    format: str


@router.post(
    "/create",
    response_model=MapResponse,
    operation_id="create_map",
    summary="Create a map project",
)
async def create_map(
    map_request: MapCreateRequest,
    session: UserContext = Depends(verify_session_required),
):
    """Creates a new map project.

    This endpoint returns both a map id `id` and project id `project_id`. Projects
    can contain multiple map versions ("maps"), unattached layer data, and details
    a history of changes to the project. Each edit will create a new map version.

    Accepts both `title` and `description` in the request body.
    """
    owner_id = session.get_user_id()

    # Generate unique IDs for project and map
    project_id = generate_id(prefix="P")
    map_id = generate_id(prefix="M")

    # Connect to database
    async with get_async_db_connection() as conn:
        # First create a project
        await conn.execute(
            """
            INSERT INTO user_mundiai_projects
            (id, owner_uuid, link_accessible, maps, title)
            VALUES ($1, $2, FALSE, ARRAY[$3], $4)
            """,
            project_id,
            owner_id,
            map_id,
            map_request.title,
        )

        # Then insert map with data including project_id and layer_ids
        result = await conn.fetchrow(
            """
            INSERT INTO user_mundiai_maps
            (id, project_id, owner_uuid, title, description, display_as_diff)
            VALUES ($1, $2, $3, $4, $5, TRUE)
            RETURNING id, title, description, created_on, last_edited
            """,
            map_id,
            project_id,
            owner_id,
            map_request.title,
            map_request.description,
        )

        # Validate the result
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database operation returned no result",
            )

        # Return the created map data
        return MapResponse(
            id=map_id,
            project_id=project_id,
            title=result["title"],
            description=result["description"],
            created_on=result["created_on"].isoformat(),
            last_edited=result["last_edited"].isoformat(),
        )


@router.get(
    "/{map_id}",
    operation_id="get_map",
)
async def get_map_route(
    request: Request,
    diff_map_id: Optional[str] = None,
    map: MundiMap = Depends(get_map),
    session: UserContext = Depends(verify_session_optional),
):
    # Ensure map is part of a project
    if not map.project_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Map is not part of a project",
        )

    async with get_async_db_connection() as conn:
        # Load project and its changelog
        project = await conn.fetchrow(
            """
            SELECT maps, map_diff_messages
            FROM user_mundiai_projects
            WHERE id = $1 AND soft_deleted_at IS NULL
            """,
            map.project_id,
        )
        if not project:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Project not found",
            )
        # Handle diff_map_id logic
        prev_map_id = None
        if diff_map_id == "auto":
            # Find the previous map in the project
            proj_maps = project["maps"] or []
            try:
                current_index = proj_maps.index(map.id)
                if current_index > 0:
                    prev_map_id = proj_maps[current_index - 1]
            except ValueError:
                pass  # map_id not found in project maps
        elif diff_map_id:
            prev_map_id = diff_map_id

        # Get last_edited times for maps in the project
        map_ids = project["maps"] or []
        if map_ids:
            map_edit_rows = await conn.fetch(
                """
                SELECT id, last_edited
                FROM user_mundiai_maps
                WHERE id = ANY($1)
                """,
                map_ids,
            )
            map_edit_times = {row["id"]: row["last_edited"] for row in map_edit_rows}
        else:
            map_edit_times = {}

        proj_maps = project["maps"] or []
        diff_msgs = project["map_diff_messages"] or []
        diff_msgs = diff_msgs + ["current edit"]
        changelog = []
        # Pair each diff message with its resulting map state up to current
        for msg, state in zip(diff_msgs, proj_maps):
            changelog.append(
                {
                    "message": msg,
                    "map_state": state,
                    "last_edited": map_edit_times.get(state).isoformat()
                    if state in map_edit_times
                    else None,
                }
            )

        # Get layer IDs from the map
        layer_ids = map.layers if map.layers else []

        # Load layers using the layer IDs
        layers = await conn.fetch(
            """
            SELECT layer_id AS id,
                    name,
                    type,
                    metadata,
                    bounds,
                    geometry_type,
                    feature_count
            FROM map_layers
            WHERE layer_id = ANY($1)
            ORDER BY id
            """,
            layer_ids,
        )
        # Convert Record objects to mutable dictionaries
        layers = [dict(layer) for layer in layers]
        for layer in layers:
            if layer.get("metadata") and isinstance(layer["metadata"], str):
                layer["metadata"] = json.loads(layer["metadata"])

        # Calculate diff if prev_map_id is provided
        layer_diffs = None
        if prev_map_id:
            user_id = session.get_user_id() if session else str(map.owner_uuid)

            # Get previous map layers with their style IDs
            prev_layer_rows = await conn.fetch(
                """
                SELECT ml.layer_id, ml.name, ml.type, ml.metadata, ml.geometry_type, ml.feature_count,
                       mls.style_id
                FROM user_mundiai_maps m
                JOIN map_layers ml ON ml.layer_id = ANY(m.layers)
                LEFT JOIN map_layer_styles mls ON mls.map_id = m.id AND mls.layer_id = ml.layer_id
                WHERE m.id = $1 AND m.owner_uuid = $2 AND m.soft_deleted_at IS NULL
                """,
                prev_map_id,
                user_id,
            )
            prev_layers = {row["layer_id"]: row for row in prev_layer_rows}

            # Get current map layers with their style IDs
            current_layer_rows = await conn.fetch(
                """
                SELECT ml.layer_id, ml.name, ml.type, ml.metadata, ml.geometry_type, ml.feature_count,
                       mls.style_id
                FROM user_mundiai_maps m
                JOIN map_layers ml ON ml.layer_id = ANY(m.layers)
                LEFT JOIN map_layer_styles mls ON mls.map_id = m.id AND mls.layer_id = ml.layer_id
                WHERE m.id = $1 AND m.owner_uuid = $2 AND m.soft_deleted_at IS NULL
                """,
                map.id,
                user_id,
            )
            new_layers = {row["layer_id"]: row for row in current_layer_rows}

            # Calculate diffs
            layer_diffs = []
            all_layer_ids = set(new_layers.keys()) | set(prev_layers.keys())

            for layer_id in all_layer_ids:
                new_layer = new_layers.get(layer_id)
                prev_layer = prev_layers.get(layer_id)

                if new_layer and not prev_layer:
                    # Added layer
                    layer_diffs.append(
                        {
                            "layer_id": layer_id,
                            "name": new_layer["name"],
                            "status": "added",
                        }
                    )
                elif prev_layer and not new_layer:
                    # Removed layer
                    layer_diffs.append(
                        {
                            "layer_id": layer_id,
                            "name": prev_layer["name"],
                            "status": "removed",
                        }
                    )
                elif new_layer and prev_layer:
                    # Check for changes
                    changes = {}
                    if new_layer["name"] != prev_layer["name"]:
                        changes["name"] = {
                            "old": prev_layer["name"],
                            "new": new_layer["name"],
                        }
                    if new_layer["metadata"] != prev_layer["metadata"]:
                        changes["metadata"] = {
                            "old": prev_layer["metadata"],
                            "new": new_layer["metadata"],
                        }
                    if new_layer["style_id"] != prev_layer["style_id"]:
                        changes["style_id"] = {
                            "old": prev_layer["style_id"],
                            "new": new_layer["style_id"],
                        }

                    if changes:
                        layer_diffs.append(
                            {
                                "layer_id": layer_id,
                                "name": new_layer["name"],
                                "status": "edited",
                                "changes": changes,
                            }
                        )
                    else:
                        layer_diffs.append(
                            {
                                "layer_id": layer_id,
                                "name": new_layer["name"],
                                "status": "existing",
                            }
                        )
        elif diff_map_id == "auto" and proj_maps and map.id == proj_maps[0]:
            # If this is the first map in the project and auto diff is requested,
            # mark all layers as added
            layer_diffs = []
            for layer in layers:
                layer_diffs.append(
                    {
                        "layer_id": layer["id"],
                        "name": layer["name"],
                        "status": "added",
                    }
                )

        # Return JSON payload
        response = {
            "map_id": map.id,
            "project_id": map.project_id,
            "layers": layers,
            "changelog": changelog,
            "display_as_diff": map.display_as_diff,
        }

        if layer_diffs is not None:
            response["diff"] = {
                "prev_map_id": prev_map_id,
                "new_map_id": map.id,
                "layer_diffs": layer_diffs,
            }

        return response


@router.get(
    "/{map_id}/layers",
    operation_id="list_map_layers",
    response_model=LayersListResponse,
)
async def get_map_layers(
    map: MundiMap = Depends(get_map),
):
    async with get_async_db_connection() as conn:
        # Get all layers by their IDs using ANY() instead of f-string
        layers = await conn.fetch(
            """
            SELECT layer_id as id, name, type, raster_cog_url, metadata, bounds, geometry_type, feature_count
            FROM map_layers
            WHERE layer_id = ANY($1)
            ORDER BY id
            """,
            map.layers,
        )

        # Process metadata JSON and add feature_count for vector layers if possible
        # Convert Record objects to mutable dictionaries
        layers = [dict(layer) for layer in layers]
        for layer in layers:
            if layer["metadata"] is not None:
                # Convert metadata from JSON string to Python dict if needed
                if isinstance(layer["metadata"], str):
                    layer["metadata"] = json.loads(layer["metadata"])

            # Set feature_count from metadata if it exists
            if (
                "metadata" in layer
                and layer["metadata"]
                and "feature_count" in layer["metadata"]
            ):
                layer["feature_count"] = layer["metadata"]["feature_count"]

            # Set original_srid from metadata if it exists
            if (
                "metadata" in layer
                and layer["metadata"]
                and "original_srid" in layer["metadata"]
            ):
                layer["original_srid"] = layer["metadata"]["original_srid"]

        # Return the layers
        return LayersListResponse(map_id=map.id, layers=layers)


@router.get(
    "/{map_id}/describe",
    operation_id="get_map_description",
)
async def get_map_description(
    request: Request,
    map_id: str,
    session: UserContext = Depends(verify_session_required),
    postgis_provider: Callable = Depends(get_postgis_provider),
    layer_describer: LayerDescriber = Depends(get_layer_describer),
    connection_manager: PostgresConnectionManager = Depends(
        get_postgres_connection_manager
    ),
):
    async with get_async_db_connection() as conn:
        # First check if the map exists and is accessible
        map_result = await conn.fetchrow(
            """
            SELECT id, title, description, owner_uuid
            FROM user_mundiai_maps
            WHERE id = $1 AND soft_deleted_at IS NULL
            """,
            map_id,
        )
        if not map_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Map not found"
            )

        # User must own the map to access this endpoint
        if session.get_user_id() != str(map_result["owner_uuid"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must own this map to access map description",
            )
        content = []
        # Get PostgreSQL connections for this map's project with documentation
        postgres_connections = await conn.fetch(
            """
            SELECT
                ppc.id,
                ppc.connection_uri,
                ppc.connection_name,
                pps.friendly_name,
                pps.summary_md,
                pps.generated_at
            FROM project_postgres_connections ppc
            JOIN user_mundiai_maps m ON ppc.project_id = m.project_id
            LEFT JOIN project_postgres_summary pps ON ppc.id = pps.connection_id
            WHERE m.id = $1 AND ppc.soft_deleted_at IS NULL
            ORDER BY ppc.connection_name, pps.generated_at DESC
            """,
            map_id,
        )

        # Add PostgreSQL connection documentation and tables to content
        seen_connections = set()
        for connection in postgres_connections:
            # Only show the most recent documentation for each connection
            if connection["id"] in seen_connections:
                continue

            content.append(f"<PostGISConnection id={connection['id']}>")
            seen_connections.add(connection["id"])

            connection_name = (
                connection["friendly_name"]
                or connection["connection_name"]
                or "Loading..."
            )
            content.append(
                f'\n## PostGIS "{connection_name}" (ID {connection["id"]})\n'
            )

            # Add documentation if available
            if connection["summary_md"]:
                content.append("<SchemaSummary>")
                content.append(connection["summary_md"])
                content.append("</SchemaSummary>")
            else:
                content.append(
                    "No documentation available for this database connection."
                )

            # Also add live table information
            try:
                tables = await postgis_provider.get_tables_by_connection_id(
                    connection["id"], connection_manager
                )
                content.append("\n**Available Tables:** " + tables)
            except Exception:
                content.append("\nException while connecting to database.")
            content.append(f"</PostGISConnection id={connection['id']}>")

        # Get all layers for this map
        layers = await conn.fetch(
            """
            SELECT ml.layer_id, ml.name, ml.type
            FROM map_layers ml
            JOIN user_mundiai_maps m ON ml.layer_id = ANY(m.layers)
            WHERE m.id = $1
            ORDER BY ml.name
            """,
            map_id,
        )

        # Generate comprehensive description
        content.append(f"# Map: {map_result['title']}\n")

        if map_result["description"]:
            content.append(f"{map_result['description']}\n")

        # Process each layer with XML tags
        for layer in layers:
            # Get detailed description for each layer
            layer_description = await describe_layer_internal(
                layer["layer_id"], layer_describer, session.get_user_id()
            )

            # Add layer with XML tags
            content.append(f"<{layer['layer_id']}>")
            content.append(layer_description)
            content.append(f"</{layer['layer_id']}>")

        # Join all content and return as plain text response
        response_content = "\n".join(content)

        return Response(
            content=response_content,
            media_type="text/plain",
            headers={
                "Content-Disposition": f'attachment; filename="{map_result["title"]}_description.txt"',
            },
        )


@router.get(
    "/{map_id}/style.json",
    operation_id="get_map_stylejson",
    response_class=StarletteJSONResponse,
)
async def get_map_style(
    request: Request,
    map_id: str,
    only_show_inline_sources: bool = False,
    session: UserContext = Depends(verify_session_optional),
    override_layers: Optional[str] = None,
    basemap: Optional[str] = None,
    base_map: BaseMapProvider = Depends(get_base_map_provider),
):
    # Get vector layers for this map from the database
    async with async_conn("get_map_style.fetch_map") as conn:
        # First check if the map exists and is accessible
        map_result = await conn.fetchrow(
            """
            SELECT m.id, p.link_accessible, m.owner_uuid, m.layers
            FROM user_mundiai_maps m
            JOIN user_mundiai_projects p ON m.project_id = p.id
            WHERE m.id = $1 AND m.soft_deleted_at IS NULL
            """,
            map_id,
        )

    if not map_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Map not found"
        )

    # Check if map is publicly accessible
    if not map_result["link_accessible"]:
        # If not publicly accessible, verify that we have auth
        if session is None or session.get_user_id() != str(map_result["owner_uuid"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return await get_map_style_internal(
        map_id, base_map, only_show_inline_sources, override_layers, basemap
    )


@basemap_router.get(
    "/available",
    operation_id="get_available_basemaps",
    response_class=StarletteJSONResponse,
)
async def get_available_basemaps(
    base_map: BaseMapProvider = Depends(get_base_map_provider),
):
    """Get list of available basemap styles."""
    return {"styles": base_map.get_available_styles()}


async def get_map_style_internal(
    map_id: str,
    base_map: BaseMapProvider,
    only_show_inline_sources: bool = False,
    override_layers: Optional[str] = None,
    basemap: Optional[str] = None,
):
    # Get vector layers for this map from the database
    async with async_conn("get_map_style_internal.fetch_layers") as conn:
        # Get layers from the map
        map_result = await conn.fetchrow(
            """
            SELECT layers
            FROM user_mundiai_maps
            WHERE id = $1 AND soft_deleted_at IS NULL
            """,
            map_id,
        )

        if map_result is None:
            raise HTTPException(status_code=404, detail="Map not found")

        # Get layers from the layer list
        layer_ids = map_result["layers"]
        if not layer_ids:
            all_layers = []
        else:
            # Fetch metadata as well to check for cog_url_suffix
            all_layers = await conn.fetch(
                """
                SELECT ml.layer_id, ml.name, ml.type, ls.style_json as maplibre_layers, ml.feature_count, ml.bounds, ml.metadata, ml.geometry_type
                FROM map_layers ml
                LEFT JOIN map_layer_styles mls ON ml.layer_id = mls.layer_id AND mls.map_id = $1
                LEFT JOIN layer_styles ls ON mls.style_id = ls.style_id
                WHERE ml.layer_id = ANY($2)
                ORDER BY ml.id
                """,
                map_id,
                layer_ids,
            )

        vector_layers = [layer for layer in all_layers if layer["type"] == "vector"]
        # Filter for raster layers; the .cog.tif endpoint handles generation if needed
        raster_layers = [layer for layer in all_layers if layer["type"] == "raster"]
        postgis_layers = [layer for layer in all_layers if layer["type"] == "postgis"]

        def get_geometry_order(layer):
            geom_type = layer.get("geometry_type") or ""
            geom_type = geom_type.lower()
            if "polygon" in geom_type:
                return 1
            elif "line" in geom_type:
                return 2
            elif "point" in geom_type:
                return 3
            return 4  # ??

        vector_layers.sort(key=get_geometry_order)
        postgis_layers.sort(key=get_geometry_order)

    style_json = await base_map.get_base_style(basemap)

    # compute combined WGS84 bounds from all_layers and derive center + zoom with 20% padding
    bounds_list = [layer["bounds"] for layer in all_layers if layer.get("bounds")]
    ZOOM_PADDING_PCT = 25
    if bounds_list:
        xs = [b[0] for b in bounds_list] + [b[2] for b in bounds_list]
        ys = [b[1] for b in bounds_list] + [b[3] for b in bounds_list]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        # apply 1/2 padding on each side
        pad_x = (max_x - min_x) * ZOOM_PADDING_PCT / 100
        pad_y = (max_y - min_y) * ZOOM_PADDING_PCT / 100
        min_x -= pad_x
        max_x += pad_x
        min_y -= pad_y
        max_y += pad_y
        # final bounds and center
        style_json["center"] = [(min_x + max_x) / 2, (min_y + max_y) / 2]
        # calculate zoom to fit both longitude and latitude spans
        lon_span = max_x - min_x
        lat_span = max_y - min_y
        zoom_lon = math.log2(360.0 / lon_span) if lon_span else None
        zoom_lat = math.log2(180.0 / lat_span) if lat_span else None
        # use the smaller zoom level to ensure both dimensions fit
        zoom = (
            min(zoom_lon, zoom_lat) if zoom_lon and zoom_lat else zoom_lon or zoom_lat
        )
        if zoom is not None and zoom > 0.0:
            style_json["zoom"] = zoom

    if override_layers is not None:
        override_layers = json.loads(override_layers)

    # If no sources in the style, initialize it
    if "sources" not in style_json:
        style_json["sources"] = {}

    # Add COG raster layers to the style if not only showing inline sources
    if not only_show_inline_sources:
        for idx, layer in enumerate(raster_layers, 1):
            layer_id = layer["layer_id"]
            source_id = f"cog-source-{layer_id}"
            cog_url = f"cog:///api/layer/{layer_id}.cog.tif"

            # Generate suffix from raster_value_stats_b1
            metadata = json.loads(layer.get("metadata", "{}"))
            if metadata and "raster_value_stats_b1" in metadata:
                min_val = metadata["raster_value_stats_b1"]["min"]
                max_val = metadata["raster_value_stats_b1"]["max"]
                cog_url += f"#color:BrewerSpectral9,{min_val},{max_val},c"

            style_json["sources"][source_id] = {
                "type": "raster",
                "url": cog_url,
                "tileSize": 256,
            }
            style_json["layers"].append(
                {
                    "id": f"raster-layer-{layer_id}",
                    "type": "raster",
                    "source": source_id,
                }
            )

    # Add vector layers as sources and layers to the style
    for idx, layer in enumerate(vector_layers, 1):
        layer_id = layer["layer_id"]

        # Use GeoJSON or PMTiles based on the only_show_inline_sources parameter
        if only_show_inline_sources:
            # For rendering, also get a presigned URL for PMTiles if available
            metadata = json.loads(layer.get("metadata", "{}"))
            pmtiles_key = metadata.get("pmtiles_key")
            assert pmtiles_key is not None

            bucket_name = get_bucket_name()
            s3_client = await get_async_s3_client()

            presigned_url = await s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_name, "Key": pmtiles_key},
                ExpiresIn=180,  # URL valid for 3 minutes
            )

            style_json["sources"][layer_id] = {
                "type": "vector",
                "url": f"pmtiles://{presigned_url}",
            }
        else:
            # Default to PMTiles
            style_json["sources"][layer_id] = {
                "type": "vector",
                "url": f"pmtiles:///api/layer/{layer_id}.pmtiles",
            }

        # Check if override_layers is not None
        if override_layers is not None and layer_id in override_layers:
            for ml_layer in override_layers[layer_id]:
                # source-layer is prohibited for geojson sources
                if style_json["sources"][layer_id]["type"] == "geojson":
                    assert ml_layer["source-layer"] == "reprojectedfgb"
                    del ml_layer["source-layer"]
                    assert "source-layer" not in ml_layer
                style_json["layers"].append(ml_layer)
        # Use stored style_json from layer_styles if no override_layers
        elif layer["maplibre_layers"]:
            for ml_layer in json.loads(layer["maplibre_layers"]):
                style_json["layers"].append(ml_layer)

    for layer in postgis_layers:
        if layer["type"] == "postgis":
            layer_id = layer["layer_id"]

            style_json["sources"][layer_id] = {
                "type": "vector",
                "tiles": [
                    f"{os.getenv('WEBSITE_DOMAIN')}/api/layer/{layer_id}/{{z}}/{{x}}/{{y}}.mvt"
                ],
                "minzoom": 0,
                "maxzoom": 17,
            }

            # Check if override_layers is not None
            if override_layers is not None and layer_id in override_layers:
                for ml_layer in override_layers[layer_id]:
                    style_json["layers"].append(ml_layer)
            # Use stored style_json from layer_styles if no override_layers
            elif layer["maplibre_layers"]:
                for ml_layer in json.loads(layer["maplibre_layers"]):
                    style_json["layers"].append(ml_layer)

    # We use globe
    style_json["projection"] = {
        "type": "globe",
    }

    # Add pointer positions source and layers for real-time collaboration
    style_json["sources"]["pointer-positions"] = {
        "type": "geojson",
        "data": {"type": "FeatureCollection", "features": []},
    }

    # label layers should be higher z-index than geometry layers. maintain order otherwise
    non_symbol_layers = [
        layer for layer in style_json["layers"] if layer.get("type") != "symbol"
    ]
    symbol_layers = [
        layer for layer in style_json["layers"] if layer.get("type") == "symbol"
    ]
    style_json["layers"] = non_symbol_layers + symbol_layers

    # Add cursor layer
    style_json["layers"].append(
        {
            "id": "pointer-cursors",
            "type": "symbol",
            "source": "pointer-positions",
            "layout": {
                "icon-image": "remote-cursor",
                "icon-size": 0.45,
                "icon-allow-overlap": True,
            },
        }
    )

    # Add labels layer
    style_json["layers"].append(
        {
            "id": "pointer-labels",
            "type": "symbol",
            "source": "pointer-positions",
            "layout": {
                "text-field": ["get", "abbrev"],
                "text-offset": [1, 1],
                "text-anchor": "top-left",
                "text-size": 11,
                "text-allow-overlap": True,
                "text-ignore-placement": True,
            },
            "paint": {
                "text-color": "#000000",
                "text-halo-color": "#FFFFFF",
                "text-halo-width": 1,
            },
        }
    )

    # Return the augmented style
    return style_json


@router.post(
    "/{original_map_id}/layers",
    response_model=LayerUploadResponse,
    operation_id="upload_layer_to_map",
    summary="Upload file as layer",
)
async def upload_layer(
    original_map_id: str,
    forked_map: MundiMap = Depends(forked_map_by_user),
    file: UploadFile = File(...),
    layer_name: str = Form(None),
    add_layer_to_map: bool = Form(True),
    session: UserContext = Depends(verify_session_required),
):
    """Uploads spatial data, processes it, and adds it as a layer to the specified map.

    Supported formats:
    - Vector: Shapefile (as .zip), GeoJSON, GeoPackage, FlatGeobuf
    - Raster: GeoTIFF, DEM
    - [Point cloud](/guides/visualizing-point-clouds-las-laz/): LAZ, LAS

    Once uploaded, Mundi transforms, reprojects, styles, and creates optimized formats for display in the browser.
    Vector data is converted to [PMTiles](https://docs.protomaps.com/pmtiles/) while raster data is converted to
    [cloud-optimized GeoTIFFs](https://cogeo.org/). Point cloud data is compressed to LAZ 1.3.

    Returns the new layer details including its unique layer ID. The layer can optionally not be added to the map,
    but will be faster to add to an existing map later.
    """
    layer_result = await internal_upload_layer(
        map_id=forked_map.id,
        file=file,
        layer_name=layer_name,
        add_layer_to_map=add_layer_to_map,
        user_id=session.get_user_id(),
        project_id=forked_map.project_id,
    )

    return LayerUploadResponse(
        dag_child_map_id=forked_map.id,
        dag_parent_map_id=original_map_id,
        id=layer_result.id,
        name=layer_result.name,
        type=layer_result.type,
        url=layer_result.url,
        message=layer_result.message,
    )


async def internal_upload_layer(
    map_id: str,
    file: UploadFile,
    layer_name: str,
    add_layer_to_map: bool,
    user_id: str,
    project_id: str,
):
    """Internal function to upload a layer without auth checks."""

    # Connect to database
    async with get_async_db_connection() as conn:
        bucket_name = get_bucket_name()

        # Generate a unique filename for the uploaded file
        filename = file.filename
        file_basename, file_ext = os.path.splitext(filename)
        file_ext = file_ext.lower()

        # If layer_name is not provided, use the filename without extension
        if not layer_name:
            layer_name = file_basename
        # Determine layer type based on file extension
        layer_type = "vector"
        if file_ext in [".tif", ".tiff", ".jpg", ".jpeg", ".png", ".dem"]:
            layer_type = "raster"
            if not file_ext:
                file_ext = ".tif"  # Default raster extension
        elif file_ext in [".las", ".laz"]:
            layer_type = "point_cloud"
        else:
            if not file_ext:
                file_ext = ".geojson"  # Default vector extension

        # Initialize metadata dictionary
        metadata_dict = {"original_filename": filename}
        bounds = None

        # Generate a unique layer ID
        layer_id = generate_id(prefix="L")

        # Generate S3 key using user UUID, project ID and layer ID
        s3_key = f"uploads/{user_id}/{project_id}/{layer_id}{file_ext}"

        # Create S3 client
        s3_client = await get_async_s3_client()
        bucket_name = get_bucket_name()

        # Save uploaded file to a temporary location
        # Preserve original file extension for GDAL/OGR format detection
        filename = file.filename
        file_ext = os.path.splitext(filename)[1].lower()

        auxiliary_temp_file_path = None
        with tempfile.NamedTemporaryFile(suffix=file_ext) as temp_file:
            # Read file content
            content = await file.read()
            # Track file size in bytes
            file_size_bytes = len(content)
            # Write to temp file
            temp_file.write(content)
            temp_file.flush()
            temp_file_path = temp_file.name
            # convert csvs to flatgeobufs
            if file_ext == ".csv":
                auxiliary_temp_file_path = temp_file_path + ".fgb"

                # Detect column names for X/Y in a case-insensitive way from the header
                # Decode a small portion; use utf-8-sig to strip BOM if present
                sample_text = content.decode("utf-8-sig", errors="replace")
                reader = csv.reader(StringIO(sample_text))

                normalized = {h.strip().lower(): h for h in next(reader, [])}
                detected_x = next(
                    (
                        normalized[col]
                        for col in ["lon", "long", "longitude", "lng", "x"]
                        if col in normalized
                    ),
                    None,
                )
                detected_y = next(
                    (
                        normalized[col]
                        for col in ["lat", "latitude", "y"]
                        if col in normalized
                    ),
                    None,
                )

                if not detected_x or not detected_y:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "CSV header must include longitude and latitude columns. "
                            "Accepted names (case-insensitive): "
                            "X: lon, long, longitude, lng, x; "
                            "Y: lat, latitude, y."
                        ),
                    )

                ogr_cmd = [
                    "ogr2ogr",
                    "-if",
                    "CSV",
                    "-f",
                    "FlatGeobuf",
                    auxiliary_temp_file_path,
                    temp_file_path,
                    "-oo",
                    f"X_POSSIBLE_NAMES={detected_x}",
                    "-oo",
                    f"Y_POSSIBLE_NAMES={detected_y}",
                    "-lco",
                    "SPATIAL_INDEX=YES",
                    "-a_srs",
                    "EPSG:4326",
                ]
                try:
                    process = await asyncio.create_subprocess_exec(
                        *ogr_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode != 0:
                        raise subprocess.CalledProcessError(
                            process.returncode, ogr_cmd, stderr=stderr.decode()
                        )

                    file_ext = ".fgb"
                    s3_key = f"uploads/{user_id}/{project_id}/{layer_id}{file_ext}"
                    temp_file_path = auxiliary_temp_file_path

                    metadata_dict["original_format"] = "csv"

                except subprocess.CalledProcessError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to convert CSV to spatial format, make sure CSV has a column named lat/lon/long/lng, latitude/longitude, or x/y.",
                    )
            # convert kml/kmz to flatgeobufs
            elif file_ext in [".kml", ".kmz"]:
                auxiliary_temp_file_path = temp_file_path + ".fgb"
                temp_dir = None

                # If this is a KMZ file, extract the KML first
                if file_ext == ".kmz":
                    try:
                        kml_file_path, temp_dir = process_kmz_to_kml(temp_file_path)
                        temp_file_path = kml_file_path
                    except ValueError as e:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"KMZ file does not contain any KML files: {str(e)}",
                        )
                    except Exception as e:
                        if temp_dir:
                            import shutil

                            shutil.rmtree(temp_dir, ignore_errors=True)
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Error processing KMZ file: {str(e)}",
                        )

                ogr_cmd = [
                    "ogr2ogr",
                    "-f",
                    "FlatGeobuf",
                    auxiliary_temp_file_path,
                    temp_file_path,
                    "-lco",
                    "SPATIAL_INDEX=YES",
                ]
                try:
                    process = await asyncio.create_subprocess_exec(
                        *ogr_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode != 0:
                        raise subprocess.CalledProcessError(
                            process.returncode, ogr_cmd, stderr=stderr.decode()
                        )

                    file_ext = ".fgb"
                    s3_key = f"uploads/{user_id}/{project_id}/{layer_id}{file_ext}"
                    temp_file_path = auxiliary_temp_file_path

                    metadata_dict["original_format"] = (
                        "kml" if file_ext == ".kml" else "kmz"
                    )

                except subprocess.CalledProcessError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to convert KML/KMZ to spatial format. Please check that the file is valid.",
                    )
                finally:
                    # Clean up temp directory if it exists
                    if temp_dir:
                        import shutil

                        shutil.rmtree(temp_dir, ignore_errors=True)

            # If this is a ZIP file, process it for shapefiles and convert to GeoPackage
            temp_dir = None
            if file_ext.lower() == ".zip":
                try:
                    # Process the ZIP file to extract and convert shapefiles to GeoPackage
                    gpkg_file_path, temp_dir = await process_zip_with_shapefile(
                        temp_file_path
                    )

                    # Update file path and extension to use the converted GeoPackage
                    temp_file_path = gpkg_file_path
                    file_ext = ".gpkg"

                    # Update S3 key to reflect the new file type
                    unique_filename = f"{uuid.uuid4()}.gpkg"
                    s3_key = f"uploads/{map_id}/{unique_filename}"

                    # Update metadata to indicate this was converted from a shapefile
                    metadata_dict.update(
                        {
                            "original_format": "shapefile_zip",
                            "converted_to": "gpkg",
                        }
                    )

                    # Update layer type
                    layer_type = "vector"
                except ValueError as e:
                    print(f"Error processing ZIP file: {str(e)}")
                    # If no shapefile is found in the ZIP, raise an error
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"ZIP file does not contain any shapefiles: {str(e)}",
                    )
                except Exception as e:
                    print(f"Error processing ZIP file: {str(e)}")
                    # Clean up temp directory if it exists
                    if temp_dir:
                        import shutil

                        shutil.rmtree(temp_dir, ignore_errors=True)
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Error processing ZIP file: {str(e)}",
                    )
            elif layer_type == "point_cloud":
                # handle it here because we're only going to upload .laz files
                import laspy
                import pyproj

                with tracer.start_as_current_span("internal_upload_layer.laspy"):
                    las = laspy.read(temp_file_path)

                    # centre of the header bounding box
                    mid_x = (las.header.mins[0] + las.header.maxs[0]) / 2
                    mid_y = (las.header.mins[1] + las.header.maxs[1]) / 2

                    src_crs = las.header.parse_crs()
                    if src_crs is None:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Point cloud file (.las, .laz) does not have a CRS, which is required to display on the map",
                        )

                    # Create transformer for CRS conversion
                    transformer = pyproj.Transformer.from_crs(
                        src_crs, 4326, always_xy=True
                    )

                    # lon/lat in WGS-84 for anchor point
                    lon, lat = transformer.transform(mid_x, mid_y)

                    # Calculate bounds in WGS84
                    min_x, min_y, min_z = las.header.mins
                    max_x, max_y, max_z = las.header.maxs

                # Transform bounds to WGS84
                min_lon, min_lat = transformer.transform(min_x, min_y)
                max_lon, max_lat = transformer.transform(max_x, max_y)

                bounds = [min_lon, min_lat, max_lon, max_lat]

                metadata_dict["pointcloud_anchor"] = {"lon": lon, "lat": lat}
                metadata_dict["pointcloud_z_range"] = [min_z, max_z]

                # generate a new .laz file
                temp_dir = tempfile.mkdtemp()
                auxiliary_temp_file_path = os.path.join(temp_dir, "4326.laz")
                las2las_cmd = [
                    "las2las64",
                    "-i",
                    temp_file_path,
                    "-set_version",
                    "1.3",
                    "-proj_epsg",
                    "4326",
                    "-o",
                    auxiliary_temp_file_path,
                ]

                try:
                    with tracer.start_as_current_span("internal_upload_layer.las2las"):
                        process = await asyncio.create_subprocess_exec(*las2las_cmd)
                        await process.wait()

                    # Check if output file was created and is valid using lasinfo64
                    if not os.path.exists(auxiliary_temp_file_path):
                        raise Exception("las2las did not create output file")

                    # Validate the output file using lasinfo64
                    lasinfo_cmd = ["lasinfo64", auxiliary_temp_file_path]
                    lasinfo_process = await asyncio.create_subprocess_exec(
                        *lasinfo_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await lasinfo_process.wait()

                    if lasinfo_process.returncode != 0:
                        raise Exception(
                            f"Output file validation failed - lasinfo64 returned exit code {lasinfo_process.returncode}"
                        )

                except Exception as e:
                    print(f"Error converting point cloud to EPSG:4326: {str(e)}")
                    raise e
                # upload the new .laz file instead
                temp_file_path = auxiliary_temp_file_path

            # Upload file to S3/MinIO
            await s3_client.upload_file(
                temp_file_path, bucket_name, s3_key, Config=one_shot_config
            )

            # Get layer bounds using GDAL
            geometry_type = "unknown"
            feature_count = None
            if layer_type == "raster":
                # Use GDAL to get bounds for raster files
                ds = gdal.Open(temp_file_path)
                if ds:
                    gt = ds.GetGeoTransform()
                    width = ds.RasterXSize
                    height = ds.RasterYSize

                    # Calculate corner coordinates
                    xmin = gt[0]
                    ymax = gt[3]
                    xmax = gt[0] + width * gt[1] + height * gt[2]
                    ymin = gt[3] + width * gt[4] + height * gt[5]

                    bounds = [xmin, ymin, xmax, ymax]

                    # Check if CRS is not EPSG:4326
                    src_crs = ds.GetProjection()
                    if src_crs:
                        # Store EPSG code if available
                        src_srs = osr.SpatialReference()
                        src_srs.ImportFromWkt(src_crs)
                        epsg_code = src_srs.GetAuthorityCode(None)
                        if epsg_code:
                            metadata_dict["original_srid"] = int(epsg_code)

                    if (
                        src_crs
                        and "EPSG:4326" not in src_crs
                        and "WGS84" not in src_crs
                    ):
                        # Create transformer from source CRS to WGS84
                        src_srs = osr.SpatialReference()
                        src_srs.ImportFromWkt(src_crs)
                        transformer = Transformer.from_crs(
                            src_srs.ExportToProj4(), "EPSG:4326", always_xy=True
                        )

                        # Transform the bounds
                        xmin, ymin = transformer.transform(bounds[0], bounds[1])
                        xmax, ymax = transformer.transform(bounds[2], bounds[3])

                        bounds = [xmin, ymin, xmax, ymax]

                    # Get statistics for single-band rasters
                    if ds.RasterCount == 1:
                        try:
                            band = ds.GetRasterBand(1)
                            # ComputeStatistics(approx_ok, force)
                            stats = band.ComputeStatistics(
                                False
                            )  # [min, max, mean, stdev]
                            min_val, max_val = stats[0], stats[1]
                            metadata_dict["raster_value_stats_b1"] = {
                                "min": min_val,
                                "max": max_val,
                            }
                        except Exception as e:
                            print(f"Error computing raster statistics: {str(e)}")

                    # Close dataset
                    ds = None
            elif layer_type == "point_cloud":
                # handled above
                pass
            else:
                # Use shared utility for vector bounds and metadata extraction
                layer_info = await get_layer_bounds_and_metadata(
                    temp_file_path, layer_type
                )
                bounds = layer_info["bounds"]
                geometry_type = layer_info["geometry_type"]
                feature_count = layer_info["feature_count"]
                metadata_dict.update(layer_info["metadata_updates"])

            # Generate MapLibre layers for vector layers
            maplibre_layers = None
            if layer_type == "vector" and geometry_type:
                maplibre_layers = generate_maplibre_layers_for_layer_id(
                    layer_id, geometry_type
                )

            new_layer_result = await conn.fetchrow(
                """
                INSERT INTO map_layers
                (layer_id, owner_uuid, name, type, metadata, bounds, geometry_type, feature_count, s3_key, size_bytes, source_map_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING layer_id
                """,
                layer_id,
                user_id,
                layer_name,
                layer_type,
                json.dumps(metadata_dict),
                bounds,
                geometry_type if layer_type == "vector" else None,
                feature_count,
                s3_key,
                file_size_bytes,
                map_id,
            )

            new_layer_id = new_layer_result["layer_id"]

            # If adding layer to map, update the map with the new layer
            if add_layer_to_map:
                # First get the current layers array
                map_data = await conn.fetchrow(
                    """
                    SELECT layers FROM user_mundiai_maps
                    WHERE id = $1
                    """,
                    map_id,
                )
                current_layers = (
                    map_data["layers"] if map_data and map_data["layers"] else []
                )

                # Then update with the new layer appended
                await conn.execute(
                    """
                    UPDATE user_mundiai_maps
                    SET layers = $1,
                        last_edited = CURRENT_TIMESTAMP
                    WHERE id = $2
                    """,
                    current_layers + [new_layer_id],
                    map_id,
                )

            # Create direct URL for the layer based on type
            layer_url = (
                f"/api/layer/{new_layer_id}.pmtiles"
                if layer_type == "vector"
                else f"/api/layer/{new_layer_id}.cog.tif"
            )

            # If this is a vector layer, create a style for it
            if layer_type == "vector" and geometry_type:
                maplibre_layers = generate_maplibre_layers_for_layer_id(
                    new_layer_id, geometry_type
                )

                # Create a default style entry
                style_id = generate_id(prefix="S")
                await conn.execute(
                    """
                    INSERT INTO layer_styles
                    (style_id, layer_id, style_json, created_by)
                    VALUES ($1, $2, $3, $4)
                    """,
                    style_id,
                    new_layer_id,
                    json.dumps(maplibre_layers),
                    user_id,
                )

                # Link the style to the map
                await conn.execute(
                    """
                    INSERT INTO map_layer_styles (map_id, layer_id, style_id)
                    VALUES ($1, $2, $3)
                    """,
                    map_id,
                    new_layer_id,
                    style_id,
                )

                # Generate PMTiles for vector layers
                if feature_count is not None and feature_count > 0:
                    # Generate PMTiles asynchronously using shared function
                    pmtiles_key = await generate_pmtiles_from_ogr_source(
                        new_layer_id,
                        temp_file_path,
                        feature_count,
                        user_id,
                        project_id,
                    )

                    # Update metadata with PMTiles key
                    result = await conn.fetchrow(
                        """
                        SELECT metadata FROM map_layers
                        WHERE layer_id = $1
                        """,
                        new_layer_id,
                    )
                    metadata = result["metadata"] if result["metadata"] else {}
                    # Parse metadata JSON if it's a string
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata)
                    metadata["pmtiles_key"] = pmtiles_key

                    # Update the database
                    await conn.execute(
                        """
                        UPDATE map_layers
                        SET metadata = $1
                        WHERE layer_id = $2
                        """,
                        json.dumps(metadata),
                        new_layer_id,
                    )

            # Cleanup temp_dir if it exists
            if temp_dir:
                import shutil

                shutil.rmtree(temp_dir, ignore_errors=True)

            # Return success response
            return InternalLayerUploadResponse(
                id=new_layer_id, name=layer_name, type=layer_type, url=layer_url
            )


@router.post(
    "/{original_map_id}/layers/remote",
    response_model=LayerUploadResponse,
    operation_id="add_remote_layer_to_map",
    summary="Add remote layer to map",
)
async def add_remote_layer(
    original_map_id: str,
    request: RemoteLayerRequest,
    forked_map: MundiMap = Depends(forked_map_by_user),
    session: UserContext = Depends(verify_session_required),
):
    """Add a remote data source as a layer to the specified map.

    Supported remote sources:
    - Cloud Optimized GeoTIFFs (COG)
    - Remote vector files (GeoJSON, Shapefile, etc.)
    - Google Sheets (CSV export format)
    - WFS services (Web Feature Service)
    - ESRI Feature Services and Map Services
    - Any OGR/GDAL compatible URL

    The remote data is accessed via OGR's vsicurl virtual file system or appropriate drivers,
    allowing efficient access to cloud-optimized formats without downloading the entire file.
    """

    validate_remote_url(request.url, request.source_type)

    # Assert URL format matches the declared source type
    if request.source_type == "sheets":
        assert request.url.startswith("CSV:"), (
            f"Google Sheets source must use CSV: prefix, got: {request.url}"
        )
    elif request.source_type == "vector":
        # Vector sources can be direct URLs or WFS services
        if request.url.startswith("WFS:"):
            # WFS URLs are valid vector sources
            pass
        elif request.url.startswith("http"):
            # Direct HTTP URLs for vector files
            pass
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid vector source URL format: {request.url}",
            )
    elif request.source_type == "raster":
        # Raster sources should be direct URLs
        if not request.url.startswith("http"):
            raise HTTPException(
                status_code=400,
                detail=f"Raster sources must be HTTP URLs, got: {request.url}",
            )
    else:
        raise HTTPException(
            status_code=400, detail=f"Unsupported source type: {request.source_type}"
        )

    # Determine file type from URL
    from urllib.parse import urlparse

    # Check if this is a CSV source (Google Sheets)
    if request.url.startswith("CSV:"):
        layer_type = "vector"  # CSV is treated as vector data
    else:
        # Regular URL - determine type from extension
        from pathlib import Path

        parsed_url = urlparse(request.url)
        file_ext = Path(parsed_url.path).suffix.lower()

        # Determine layer type based on file extension
        layer_type = "vector"
        if file_ext in [".tif", ".tiff", ".jpg", ".jpeg", ".png", ".dem"]:
            layer_type = "raster"
        elif file_ext in [".geojson", ".fgb", ".gpkg", ".shp"]:
            layer_type = "vector"
        else:
            # Default to vector, let validation determine if it fails
            layer_type = "vector"

        # Special handling for WFS (Web Feature Service) URLs
        # WFS URLs contain service protocol parameters and should not use /vsicurl/ prefix
        # Validation will be handled during processing for both WFS and regular URLs

    # Handle file processing - CSV sources don't need downloading
    import tempfile

    if request.url.startswith("CSV:"):
        # For CSV sources, we don't download - we process directly with OGR
        # Estimate file size by getting content length
        import aiohttp

        try:
            # Extract the actual URL from CSV:/vsicurl/URL format
            actual_url = request.url.replace("CSV:/vsicurl/", "")
            async with aiohttp.ClientSession() as http_session:
                async with http_session.head(actual_url) as response:
                    file_size_bytes = int(response.headers.get("content-length", 0))
                    if file_size_bytes == 0:
                        file_size_bytes = 1000  # Default estimate for CSV
        except Exception:
            file_size_bytes = 1000  # Default estimate if head request fails

        # We'll process this directly with OGR later without downloading
        file_content = None
    elif (
        "SERVICE=WFS" in request.url.upper()
        and "REQUEST=GETFEATURE" in request.url.upper()
    ):
        # WFS services should NOT be downloaded - they're processed directly with OGR
        # Estimate file size for WFS (we can't really know without processing)
        file_size_bytes = 10000  # Default estimate for WFS response
        file_content = None
    else:
        # Download remote file temporarily for processing while maintaining remote status
        import aiohttp

        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(request.url) as response:
                if response.status != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Unable to download remote file: HTTP {response.status}",
                    )

                file_content = await response.read()
                file_size_bytes = len(file_content)

    # Process the file using similar logic to internal_upload_layer
    layer_id = generate_id(prefix="L")

    # Handle file processing differently for CSV sources vs downloaded files
    auxiliary_temp_file_path = None
    temp_file_path = None

    if request.url.startswith("CSV:"):
        # For CSV sources, we work directly with the remote URL
        # Set file extension for CSV processing
        file_ext = ".csv"
        ogr_source = request.url  # Use the full CSV:/vsicurl/... URL
    elif (
        "SERVICE=WFS" in request.url.upper()
        and "REQUEST=GETFEATURE" in request.url.upper()
    ):
        # For WFS sources, we work directly with the remote URL
        file_ext = ".gml"  # WFS typically returns GML
        ogr_source = request.url  # Use the WFS URL directly
    elif (
        "/FeatureServer" in request.url or "/MapServer" in request.url
    ) and "/query" in request.url:
        # For ESRI Feature Service or Map Service URLs - use ESRIJSON driver with prefix
        file_ext = ".geojson"  # ESRI services return GeoJSON-like data
        ogr_source = f"ESRIJSON:{request.url}"  # Use ESRIJSON driver prefix
    else:
        # Save downloaded content to temporary file for processing
        import os

        file_ext = os.path.splitext(urlparse(request.url).path)[1]
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as temp_file:
            temp_file.write(file_content)
            temp_file.flush()
            temp_file_path = temp_file.name
            ogr_source = temp_file_path

    # Convert non-FlatGeobuf vector formats to FlatGeobuf for optimal PMTiles generation
    if layer_type == "vector" and file_ext != ".fgb":
        # Check if non-CSV data has geometry
        has_geometry = True
        if file_ext != ".csv" and not request.url.startswith("CSV:"):
            # For non-CSV files, check if they have existing geometry
            try:
                with fiona.open(ogr_source) as collection:
                    # Check if schema has geometry field
                    if not collection.schema or "geometry" not in collection.schema:
                        has_geometry = False
                        print("DEBUG: Non-CSV data has no geometry schema")
                    else:
                        # Check if any features actually have geometry
                        if len(collection) > 0:
                            first_feature = next(iter(collection))
                            if (
                                not first_feature
                                or "geometry" not in first_feature
                                or not first_feature["geometry"]
                                or first_feature["geometry"]["type"] == "null"
                            ):
                                has_geometry = False
                        else:
                            has_geometry = False
            except Exception:
                has_geometry = True  # Default to True for non-CSV files

        # Create temp file for FlatGeobuf conversion
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".fgb", delete=False) as temp_fgb:
            auxiliary_temp_file_path = temp_fgb.name
        # Remove the temp file so ogr2ogr can create it fresh
        os.remove(auxiliary_temp_file_path)

        # Build ogr2ogr command - only add spatial index if data has geometry
        ogr_cmd = [
            "ogr2ogr",
            "-overwrite",
            "-f",
            "FlatGeobuf",
            auxiliary_temp_file_path,
            ogr_source,
        ]

        # Add CSV-specific options for lat/lng column detection if processing CSV
        if file_ext == ".csv" or request.url.startswith("CSV:"):
            ogr_cmd.extend(
                [
                    "-oo",
                    "X_POSSIBLE_NAMES=lon,long,longitude,lng,x",
                    "-oo",
                    "Y_POSSIBLE_NAMES=lat,latitude,y",
                    "-oo",
                    "KEEP_GEOM_COLUMNS=NO",
                    "-a_srs",
                    "EPSG:4326",  # Assign WGS84 CRS to CSV lat/lng data
                ]
            )
            # For CSV with lat/lng columns, we can add spatial index since geometry will be created
            ogr_cmd.extend(["-lco", "SPATIAL_INDEX=YES"])
        elif has_geometry:
            ogr_cmd.extend(["-lco", "SPATIAL_INDEX=YES"])

        try:
            import asyncio

            process = await asyncio.create_subprocess_exec(
                *ogr_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, ogr_cmd, stderr=stderr.decode()
                )

            # Use the converted FlatGeobuf file for further processing
            temp_file_path = auxiliary_temp_file_path
            ogr_source = auxiliary_temp_file_path
            file_ext = ".fgb"

        except subprocess.CalledProcessError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to convert remote file to optimized format. Please check that the URL is accessible and contains valid geospatial data.",
            )

        try:
            # Initialize metadata dictionary
            if request.url.startswith("CSV:"):
                # For CSV sources, extract filename from the actual Google Sheets URL
                actual_url = request.url.replace("CSV:/vsicurl/", "")
                metadata_dict = {
                    "original_url": request.url,
                    "source": "remote",
                    "original_filename": "Google Sheets CSV Export",
                    "google_sheets_url": actual_url,
                }
            else:
                parsed_url = urlparse(request.url)
                metadata_dict = {
                    "original_url": request.url,
                    "source": "remote",
                    "original_filename": Path(parsed_url.path).name
                    or f"remote_file{file_ext}",
                }
            bounds = None
            geometry_type = "unknown"
            feature_count = None

            # Process layer based on type using shared utilities
            processing_source = temp_file_path if temp_file_path else ogr_source

            if layer_type == "vector":
                # Use shared vector processing pipeline
                layer_result = await process_vector_layer_common(
                    layer_id,
                    processing_source,
                    request.name,
                    session.get_user_id(),
                    forked_map.project_id,
                )
                bounds = layer_result["bounds"]
                geometry_type = layer_result["geometry_type"]
                feature_count = layer_result["feature_count"]
                # Use the processed metadata which includes PMTiles key
                metadata_dict = layer_result["metadata"]
                # Note: MapLibre style generation handled by process_vector_layer_common
            else:
                # Handle raster layers
                layer_info = await get_layer_bounds_and_metadata(
                    processing_source, layer_type, request.url
                )
                bounds = layer_info["bounds"]
                geometry_type = "raster"
                feature_count = None
                metadata_dict.update(layer_info["metadata_updates"])

            # Insert remote layer into database with processing metadata
            async with get_async_db_connection() as conn:
                await conn.fetchrow(
                    """
                    INSERT INTO map_layers
                    (layer_id, owner_uuid, name, type, metadata, bounds, geometry_type, feature_count, size_bytes, source_map_id, remote_url)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    RETURNING layer_id
                    """,
                    layer_id,
                    session.get_user_id(),
                    request.name,
                    layer_type,
                    json.dumps(metadata_dict),
                    bounds,
                    geometry_type if layer_type == "vector" else None,
                    feature_count,
                    file_size_bytes,
                    forked_map.id,
                    request.url,  # Store original remote URL
                )

                # For vector layers, handle style creation (PMTiles already handled by process_vector_layer_common)
                if layer_type == "vector" and geometry_type != "unknown":
                    maplibre_layers = generate_maplibre_layers_for_layer_id(
                        layer_id, geometry_type
                    )
                    style_id = generate_id(prefix="S")
                    await conn.execute(
                        """
                        INSERT INTO layer_styles
                        (style_id, layer_id, style_json, created_by)
                        VALUES ($1, $2, $3, $4)
                        """,
                        style_id,
                        layer_id,
                        json.dumps(maplibre_layers),
                        session.get_user_id(),
                    )

                    # Associate style with the map
                    await conn.execute(
                        """
                        INSERT INTO map_layer_styles (map_id, layer_id, style_id)
                        VALUES ($1, $2, $3)
                        """,
                        forked_map.id,
                        layer_id,
                        style_id,
                    )

                # Add to map if requested
                if request.add_layer_to_map:
                    map_data = await conn.fetchrow(
                        "SELECT layers FROM user_mundiai_maps WHERE id = $1",
                        forked_map.id,
                    )
                    current_layers = (
                        map_data["layers"] if map_data and map_data["layers"] else []
                    )
                    new_layers = current_layers + [layer_id]
                    await conn.execute(
                        """
                        UPDATE user_mundiai_maps
                        SET layers = $1, last_edited = CURRENT_TIMESTAMP
                        WHERE id = $2
                        """,
                        new_layers,
                        forked_map.id,
                    )

        finally:
            # Clean up temp files
            import os

            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            if auxiliary_temp_file_path and os.path.exists(auxiliary_temp_file_path):
                os.unlink(auxiliary_temp_file_path)

    # Create layer URL
    layer_url = (
        f"/api/layer/{layer_id}.pmtiles"
        if layer_type == "vector"
        else f"/api/layer/{layer_id}.cog.tif"
    )

    response = LayerUploadResponse(
        dag_child_map_id=forked_map.id,
        dag_parent_map_id=original_map_id,
        id=layer_id,
        name=request.name,
        type=layer_type,
        url=layer_url,
        message="Remote layer processed and added successfully",
    )
    return response


async def get_layer_bounds_and_metadata(
    ogr_source: str, layer_type: str, original_source: str = None
) -> dict:
    """
    Extract bounds, geometry type, feature count and other metadata from any OGR/GDAL compatible source.

    Args:
        ogr_source: Path to local file or OGR-compatible URI (CSV:/vsicurl/..., WFS:http://..., etc.)
        layer_type: 'vector', 'raster', or 'point_cloud'
        original_source: Optional original source URL (for context in error messages)

    Returns:
        dict with keys: bounds, geometry_type, feature_count, metadata_updates
    """
    bounds = None
    geometry_type = "unknown"
    feature_count = None
    metadata_updates = {}

    try:
        if layer_type == "raster":
            # Use GDAL for raster bounds extraction
            ds = gdal.Open(ogr_source)
            if ds:
                gt = ds.GetGeoTransform()
                width = ds.RasterXSize
                height = ds.RasterYSize

                # Calculate corner coordinates
                xmin = gt[0]
                ymax = gt[3]
                xmax = gt[0] + width * gt[1] + height * gt[2]
                ymin = gt[3] + width * gt[4] + height * gt[5]
                bounds = [xmin, ymin, xmax, ymax]

                # Check CRS and store EPSG code if available
                src_crs = ds.GetProjection()
                if src_crs:
                    src_srs = osr.SpatialReference()
                    src_srs.ImportFromWkt(src_crs)
                    epsg_code = src_srs.GetAuthorityCode(None)
                    if epsg_code:
                        metadata_updates["original_srid"] = int(epsg_code)

                    # Transform bounds to EPSG:4326 if needed
                    if "EPSG:4326" not in src_crs and "WGS84" not in src_crs:
                        transformer = Transformer.from_crs(
                            src_srs.ExportToProj4(), "EPSG:4326", always_xy=True
                        )
                        xmin, ymin = transformer.transform(bounds[0], bounds[1])
                        xmax, ymax = transformer.transform(bounds[2], bounds[3])
                        bounds = [xmin, ymin, xmax, ymax]

                # Get statistics for single-band rasters
                if ds.RasterCount == 1:
                    try:
                        band = ds.GetRasterBand(1)
                        stats = band.ComputeStatistics(False)  # [min, max, mean, stdev]
                        min_val, max_val = stats[0], stats[1]
                        metadata_updates["raster_value_stats_b1"] = {
                            "min": min_val,
                            "max": max_val,
                        }
                    except Exception as e:
                        print(f"Error computing raster statistics: {str(e)}")

                ds = None

        elif layer_type == "vector":
            # Use Fiona for vector bounds and metadata extraction
            with fiona.open(ogr_source) as collection:
                # Get bounds and feature count
                bounds = list(collection.bounds)
                feature_count = len(collection)
                metadata_updates["feature_count"] = feature_count

                # Detect geometry type from schema
                if collection.schema and "geometry" in collection.schema:
                    geom_type = collection.schema["geometry"]
                    geometry_type = geom_type.lower() if geom_type else "unknown"

                    # Check first feature for more specific geometry type
                    if feature_count > 0:
                        first_feature = next(iter(collection))
                        if (
                            first_feature
                            and "geometry" in first_feature
                            and "type" in first_feature["geometry"]
                        ):
                            actual_type = first_feature["geometry"]["type"].lower()
                            if actual_type and actual_type != "null":
                                geometry_type = actual_type

                # Store geometry type in metadata if not unknown
                if geometry_type != "unknown":
                    metadata_updates["geometry_type"] = geometry_type

                # Handle CRS transformation to EPSG:4326
                src_crs = collection.crs
                if src_crs:
                    # Store EPSG code if available
                    if hasattr(src_crs, "to_epsg") and src_crs.to_epsg():
                        metadata_updates["original_srid"] = src_crs.to_epsg()

                    # Transform bounds if not already EPSG:4326
                    crs_string = src_crs.to_string()
                    if (
                        "EPSG:4326" not in crs_string
                        and "WGS84" not in crs_string
                        and bounds is not None
                    ):
                        transformer = Transformer.from_crs(
                            src_crs, "EPSG:4326", always_xy=True
                        )
                        xmin, ymin = transformer.transform(bounds[0], bounds[1])
                        xmax, ymax = transformer.transform(bounds[2], bounds[3])
                        bounds = [xmin, ymin, xmax, ymax]

        # For point_cloud, we don't extract bounds here (handled elsewhere)

    except Exception as e:
        # Use original source for context if available, otherwise use ogr_source
        source_for_context = original_source or ogr_source

        # For WFS services, bounds extraction failure is common and expected
        if (
            original_source
            and "SERVICE=WFS" in original_source.upper()
            and "REQUEST=GETFEATURE" in original_source.upper()
        ):
            if "Driver was not able to calculate bounds" in str(e):
                print(
                    f"INFO: WFS service did not provide spatial bounds (this is normal): {source_for_context}"
                )
            else:
                print(
                    f"Note: WFS metadata extraction had minor issues (continuing normally): {str(e)}"
                )
        else:
            print(
                f"Error extracting layer metadata from {source_for_context}: {str(e)}"
            )
        # Return defaults on error
        pass

    return {
        "bounds": bounds,
        "geometry_type": geometry_type,
        "feature_count": feature_count,
        "metadata_updates": metadata_updates,
    }


async def generate_pmtiles_from_ogr_source(
    layer_id: str,
    ogr_source: str,
    feature_count: int,
    user_id: str = None,
    project_id: str = None,
):
    """Generate PMTiles from any OGR-compatible source and store in S3."""
    bucket_name = get_bucket_name()

    with tempfile.TemporaryDirectory() as temp_dir:
        # Create local output PMTiles file
        local_output_file = os.path.join(temp_dir, f"layer_{layer_id}.pmtiles")
        # Reproject to EPSG:4326 and convert to FlatGeobuf
        reprojected_file = os.path.join(temp_dir, "reprojected.fgb")

        # Build ogr2ogr command with source-specific options
        ogr_cmd = [
            "ogr2ogr",
            "-f",
            "FlatGeobuf",
            "-t_srs",
            "EPSG:4326",
            "-nlt",
            "PROMOTE_TO_MULTI",
            "-skipfailures",
        ]

        # Add CSV-specific options for lat/long column detection
        if ogr_source.startswith("CSV:"):
            ogr_cmd.extend(
                [
                    "-oo",
                    "X_POSSIBLE_NAMES=long,longitude,lng,x",
                    "-oo",
                    "Y_POSSIBLE_NAMES=lat,latitude,y",
                    "-oo",
                    "KEEP_GEOM_COLUMNS=NO",
                ]
            )

        ogr_cmd.extend([reprojected_file, ogr_source])

        process = await asyncio.create_subprocess_exec(
            *ogr_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(
                "Failed to reproject geospatial data. Please check that the source contains valid geometry."
            )

        # Run tippecanoe to generate pmtiles
        tippecanoe_cmd = [
            "tippecanoe",
            "-o",
            local_output_file,
            "-q",  # Quiet mode - suppress progress indicators
        ]
        if feature_count > 1:
            tippecanoe_cmd.append(
                "-zg"
            )  # Can't guess maxzoom (-zg) without at least two distinct feature locations
        tippecanoe_cmd.extend(
            [
                "--drop-densest-as-needed",
                reprojected_file,
            ]
        )

        process = await asyncio.create_subprocess_exec(*tippecanoe_cmd)
        await process.wait()

        if process.returncode != 0:
            raise Exception(
                f"tippecanoe command failed with exit code {process.returncode}"
            )

        # Upload the PMTiles file to S3 with user_id and project_id in path if available
        if user_id and project_id:
            pmtiles_key = f"pmtiles/{user_id}/{project_id}/{layer_id}.pmtiles"
        else:
            # Fallback to old path if user_id/project_id not available
            pmtiles_key = f"pmtiles/layer/{layer_id}.pmtiles"
        s3 = await get_async_s3_client()
        await s3.upload_file(
            local_output_file, bucket_name, pmtiles_key, Config=one_shot_config
        )

        # Update the database with the PMTiles key
        async with get_async_db_connection() as conn:
            # Get current metadata
            result = await conn.fetchrow(
                """
                SELECT metadata FROM map_layers
                WHERE layer_id = $1
                """,
                layer_id,
            )
            metadata = result["metadata"] if result and result["metadata"] else {}
            # Parse metadata JSON if it's a string
            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            # Update metadata with PMTiles key
            metadata["pmtiles_key"] = pmtiles_key

            # Update the database
            await conn.execute(
                """
                UPDATE map_layers
                SET metadata = $1
                WHERE layer_id = $2
                """,
                json.dumps(metadata),
                layer_id,
            )

        return pmtiles_key


async def process_vector_layer_common(
    layer_id: str, ogr_source: str, layer_name: str, user_id: str, project_id: str
) -> dict:
    """
    Unified processing pipeline for vector layers from any source.

    Args:
        layer_id: Generated layer ID
        ogr_source: OGR-compatible source (local file path, CSV:/vsicurl/..., WFS:http://..., etc.)
        layer_name: Display name for the layer
        user_id: User ID for ownership
        project_id: Project ID for organization

    Returns:
        dict with processed layer data ready for database insertion
    """
    # Extract bounds and metadata from the source
    layer_info = await get_layer_bounds_and_metadata(ogr_source, "vector")

    bounds = layer_info["bounds"]
    geometry_type = layer_info["geometry_type"]
    feature_count = layer_info["feature_count"]
    metadata_dict = layer_info["metadata_updates"].copy()

    # Add base metadata
    metadata_dict.update(
        {
            "source": "remote" if not ogr_source.startswith("/") else "upload",
            "layer_name": layer_name,
        }
    )

    # Generate PMTiles for vector layers with features
    pmtiles_key = None
    if feature_count and feature_count > 0:
        try:
            pmtiles_key = await generate_pmtiles_from_ogr_source(
                layer_id,
                ogr_source,
                feature_count,
                user_id,
                project_id,
            )
            metadata_dict["pmtiles_key"] = pmtiles_key
        except Exception as e:
            print(f"PMTiles generation failed for {ogr_source}: {e}")
            # Continue without PMTiles - not critical

    # Generate MapLibre style for vector layers
    maplibre_style = None
    if geometry_type != "unknown":
        maplibre_style = generate_maplibre_layers_for_layer_id(layer_id, geometry_type)

    return {
        "layer_id": layer_id,
        "bounds": bounds,
        "geometry_type": geometry_type,
        "feature_count": feature_count,
        "metadata": metadata_dict,
        "pmtiles_key": pmtiles_key,
        "maplibre_style": maplibre_style,
        "layer_type": "vector",
    }


@router.put("/{map_id}/layer/{layer_id}", operation_id="add_layer_to_map")
async def add_layer_to_map(
    map: MundiMap = Depends(get_map),
    layer: MapLayer = Depends(get_layer),
):
    if map.layers is not None and layer.id in map.layers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Layer is already associated with this map",
        )

    async with get_async_db_connection() as conn:
        # Update the map to include the layer_id in its layers array
        updated_map = await conn.fetchrow(
            """
            UPDATE user_mundiai_maps
            SET layers = array_append(layers, $1),
                last_edited = CURRENT_TIMESTAMP
            WHERE id = $2
            RETURNING id
            """,
            layer.id,
            map.id,
        )

        if not updated_map:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to associate layer with map",
            )

        return {
            "message": "Layer successfully associated with map",
            "layer_id": layer.id,
            "layer_name": layer.name,
            "map_id": map.id,
        }


async def pull_bounds_from_map(map_id: str) -> tuple[float, float, float, float]:
    """Pull the bounds from the map in the database by taking the min and max of all layer bounds."""
    async with get_async_db_connection() as conn:
        result = await conn.fetchrow(
            """
            SELECT
                MIN(ml.bounds[1]) as xmin,
                MIN(ml.bounds[2]) as ymin,
                MAX(ml.bounds[3]) as xmax,
                MAX(ml.bounds[4]) as ymax
            FROM map_layers ml
            JOIN user_mundiai_maps m ON ml.layer_id = ANY(m.layers)
            WHERE m.id = $1 AND ml.bounds IS NOT NULL
            """,
            map_id,
        )

        if not result or result["xmin"] is None:
            # No layers with bounds found
            return (-180, -90, 180, 90)

        return (
            result["xmin"],
            result["ymin"],
            result["xmax"],
            result["ymax"],
        )


@router.get(
    "/{map_id}/render.png",
    operation_id="render_map_to_png",
    summary="Render a map as PNG",
)
async def render_map(
    request: Request,
    map: MundiMap = Depends(get_map),
    bbox: Optional[str] = None,
    width: int = 1024,
    height: int = 600,
    bgcolor: str = "#ffffff",
    base_map: BaseMapProvider = Depends(get_base_map_provider),
    session: Optional[UserContext] = Depends(verify_session_optional),
):
    """Renders a map as a static PNG image, including layers and their symbology.

    If no `bbox` is provided, the extent defaults to the smallest extent that contains
    all layers with well-defined bounding boxes. `bbox` must be in the format `xmin,ymin,xmax,ymax` (EPSG:4326).

    Width and height are in pixels.
    """
    style_json = await get_map_style(
        request,
        map.id,
        only_show_inline_sources=True,
        session=session,
        base_map=base_map,
    )

    return (
        await render_map_internal(
            map.id, bbox, width, height, "mbgl", bgcolor, style_json
        )
    )[0]


# requires style.json to be provided, so that we can do this without auth
async def render_map_internal(
    map_id: str,
    bbox: Optional[str],
    width: int,
    height: int,
    renderer: str,
    bgcolor: str,
    style_json: str,
) -> tuple[Response, dict]:
    if bbox is None:
        xmin, ymin, xmax, ymax = await pull_bounds_from_map(map_id)
    else:
        xmin, ymin, xmax, ymax = map(float, bbox.split(","))

    assert style_json is not None
    # Create a temporary file for the output PNG
    with tempfile.NamedTemporaryFile(suffix=".png") as temp_output:
        output_path = temp_output.name

        # Format the style JSON with required parameters
        input_data = {
            "width": width,
            "height": height,
            "bounds": f"{xmin},{ymin},{xmax},{ymax}",
            "style": style_json,
            "ratio": 1,
        }

        # Get zoom and center for metadata using the zoom script
        zoom_process = await asyncio.create_subprocess_exec(
            "node",
            "src/renderer/zoom.js",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        zoom_stdout, zoom_stderr = await zoom_process.communicate(
            input=json.dumps(
                {
                    "bbox": f"{xmin},{ymin},{xmax},{ymax}",
                    "width": width,
                    "height": height,
                }
            ).encode()
        )
        zoom_data = json.loads(zoom_stdout.decode())

        # Run the renderer using subprocess
        try:
            process = await asyncio.create_subprocess_exec(
                "xvfb-run",
                "-a",
                "node",
                "src/renderer/render.js",
                output_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate(
                input=json.dumps(input_data).encode()
            )
            print(f"Render output: {stdout}")
            print(f"Render error: {stderr}")

            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, "xvfb-run", output=stdout, stderr=stderr
                )

            temp_output.seek(0)
            screenshot_data = temp_output.read()

            return (
                Response(
                    content=screenshot_data,
                    media_type="image/png",
                    headers={
                        "Content-Type": "image/png",
                        "Content-Disposition": f"inline; filename=map_{map_id}.png",
                    },
                ),
                zoom_data,
            )
        except subprocess.CalledProcessError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error rendering map: {e.stderr.decode()}",
            )


@router.delete(
    "/{original_map_id}/layer/{layer_id}",
    operation_id="remove_layer_from_map",
    response_model=LayerRemovalResponse,
)
async def remove_layer_from_map(
    original_map_id: str,
    layer_id: str,
    forked_map: MundiMap = Depends(forked_map_by_user),
):
    # Check if the layer exists and is in the map's layers array
    if layer_id not in forked_map.layers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Layer not found or not associated with this map",
        )

    async with get_async_db_connection() as conn:
        async with conn.transaction():
            # Get layer name for response
            layer_result = await conn.fetchrow(
                """
                SELECT name FROM map_layers WHERE layer_id = $1
                """,
                layer_id,
            )
            layer_name = layer_result["name"] if layer_result else "Unknown"

            # Remove the layer from the child map's layers array
            updated_layers = [lid for lid in forked_map.layers if lid != layer_id]
            await conn.execute(
                """
                UPDATE user_mundiai_maps
                SET layers = $1,
                    last_edited = CURRENT_TIMESTAMP
                WHERE id = $2
                """,
                updated_layers,
                forked_map.id,
            )

    return LayerRemovalResponse(
        dag_child_map_id=forked_map.id,
        dag_parent_map_id=original_map_id,
        layer_id=layer_id,
        layer_name=layer_name,
        message="Layer successfully removed from map",
    )


@router.get("/", operation_id="list_user_maps", response_model=UserMapsResponse)
async def get_user_maps(
    request: Request, session: UserContext = Depends(verify_session_required)
):
    """
    Get all maps owned by the authenticated user.

    Returns a list of all maps that belong to the currently authenticated user.
    Authentication is required via SuperTokens session or API key.
    """
    # Get the user ID from authentication
    user_id = session.get_user_id()

    # Connect to database
    async with get_async_db_connection() as conn:
        # Get all maps owned by this user that are not soft-deleted
        maps_data = await conn.fetch(
            """
            SELECT m.id, m.title, m.description, m.created_on, m.last_edited, p.link_accessible, m.project_id
            FROM user_mundiai_maps m
            JOIN user_mundiai_projects p ON m.project_id = p.id
            WHERE m.owner_uuid = $1 AND m.soft_deleted_at IS NULL
            ORDER BY m.last_edited DESC
            """,
            user_id,
        )

        # Convert datetime objects to ISO format strings for JSON serialization
        maps_response = []
        for map_data in maps_data:
            # Convert datetime objects to strings
            created_on = (
                map_data["created_on"].isoformat()
                if isinstance(map_data["created_on"], datetime)
                else map_data["created_on"]
            )
            last_edited = (
                map_data["last_edited"].isoformat()
                if isinstance(map_data["last_edited"], datetime)
                else map_data["last_edited"]
            )

            maps_response.append(
                {
                    "id": map_data["id"],
                    "project_id": map_data["project_id"],
                    "title": map_data["title"] or "Untitled Map",
                    "description": map_data["description"] or "",
                    "created_on": created_on,
                    "last_edited": last_edited,
                }
            )

        # Return the list of maps
        return UserMapsResponse(maps=maps_response)


# Export both routers
__all__ = ["router"]
