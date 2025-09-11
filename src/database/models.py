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

from sqlalchemy import (
    Column,
    String,
    UUID,
    TIMESTAMP,
    Boolean,
    ARRAY,
    Text,
    Integer,
    BIGINT,
    Float,
    ForeignKey,
)
import json
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from typing import TYPE_CHECKING
from datetime import datetime
import asyncio
import os
import tempfile
import time
from contextlib import asynccontextmanager

if TYPE_CHECKING:
    pass

Base = declarative_base()


class MundiProject(Base):
    __tablename__ = "user_mundiai_projects"

    id = Column(String(12), primary_key=True)  # starts with P
    owner_uuid = Column(UUID, nullable=False)
    editor_uuids = Column(ARRAY(UUID))  # list of uuids that can edit this project
    viewer_uuids = Column(ARRAY(UUID))  # list of uuids that can view this project
    link_accessible = Column(Boolean, default=False)
    title = Column(String, server_default="Untitled Map")
    maps = Column(ARRAY(String(12)))  # most recent is last
    map_diff_messages = Column(
        ARRAY(Text)
    )  # len(maps)-1 messages, each message is a diff between two maps
    created_on = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    soft_deleted_at = Column(TIMESTAMP(timezone=True))

    # Relationships
    postgres_connections = relationship(
        "ProjectPostgresConnection", back_populates="project"
    )


class MundiMap(Base):
    __tablename__ = "user_mundiai_maps"

    id = Column(String(12), primary_key=True)  # starts with M
    project_id = Column(String(12))  # No foreign key in init.sql
    owner_uuid = Column(UUID, nullable=False)
    parent_map_id: str | None = Column(
        String(12), ForeignKey("user_mundiai_maps.id"), nullable=True
    )
    layers = Column(ARRAY(String(12)))
    display_as_diff = Column(Boolean, nullable=True)  # deprecated
    title = Column(String)
    description = Column(String)
    created_on = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    last_edited = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    fork_reason = Column(String, nullable=True)
    basemap = Column(String(50), nullable=True)
    soft_deleted_at = Column(TIMESTAMP(timezone=True))

    # Relationships
    chat_completion_messages = relationship(
        "MundiChatCompletionMessage", back_populates="map"
    )
    layer_styles = relationship("MapLayerStyle", back_populates="map")
    parent_map = relationship("MundiMap", remote_side=[id])
    child_maps = relationship("MundiMap", overlaps="parent_map")


class ProjectPostgresConnection(Base):
    __tablename__ = "project_postgres_connections"

    id = Column(String(12), primary_key=True)
    project_id = Column(
        String(12), ForeignKey("user_mundiai_projects.id"), nullable=False
    )
    user_id = Column(UUID, nullable=False)
    connection_uri = Column(Text, nullable=False)
    connection_name = Column(String(255))  # Optional friendly name for the connection
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.current_timestamp()
    )
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=func.current_timestamp()
    )
    last_error_text = Column(Text, nullable=True)
    last_error_timestamp = Column(TIMESTAMP(timezone=True), nullable=True)
    soft_deleted_at = Column(TIMESTAMP(timezone=True))

    # Relationships
    project = relationship("MundiProject", back_populates="postgres_connections")
    summaries = relationship("ProjectPostgresSummary", back_populates="connection")
    layers = relationship("MapLayer", back_populates="postgis_connection")


class ProjectPostgresSummary(Base):
    __tablename__ = "project_postgres_summary"

    id = Column(String(12), primary_key=True)
    connection_id = Column(
        String(12), ForeignKey("project_postgres_connections.id"), nullable=False
    )
    friendly_name = Column(
        String(255), nullable=False
    )  # AI-generated friendly name for display
    summary_md = Column(Text, nullable=False)  # AI-generated markdown summary
    table_count = Column(Integer, nullable=True)  # Number of tables in the database
    generated_at = Column(
        TIMESTAMP(timezone=True), server_default=func.current_timestamp()
    )

    # Relationships
    connection = relationship("ProjectPostgresConnection", back_populates="summaries")


class MapLayer(Base):
    __tablename__ = "map_layers"

    id = Column(Integer)
    layer_id = Column(
        String(12), primary_key=True
    )  # 12-char unique ID for layers, starts with L
    owner_uuid = Column(UUID, nullable=False)
    name = Column(String, nullable=False)  # layer name
    s3_key = Column(String)
    type = Column(
        String, nullable=False
    )  # 'vector', 'raster', 'postgis', 'point_cloud'
    raster_cog_url = Column(String)  # DEPRECATED: unused field, can be NULL
    postgis_connection_id = Column(
        String(12), ForeignKey("project_postgres_connections.id")
    )
    postgis_query = Column(String)  # required for postgres
    postgis_attribute_column_list = Column(ARRAY(String))  # excludes id and geom
    metadata_json = Column("metadata", JSONB)
    bounds = Column(ARRAY(Float))  # [xmin, ymin, xmax, ymax] in WGS84 coordinates
    geometry_type = Column(
        String
    )  # 'point', 'multipoint', 'linestring', 'polygon', etc.
    feature_count = Column(Integer)  # Number of features in vector layers
    size_bytes = Column(BIGINT)  # Size of uploaded layer in bytes
    source_map_id = Column(String)  # Optional map ID that this layer was created from
    remote_url = Column(String)  # Optional remote URL for external data sources
    created_on = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    last_edited = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    @property
    def metadata_dict(self):
        """Return metadata as parsed JSON."""
        if self.metadata is not None:
            return json.loads(self.metadata)

    async def get_ogr_source(self, never_return_local_file: bool = False):
        """Return OGR-compatible source string for this layer

        For PostGIS layers, returns a PostgreSQL connection string with the layer's query.
        For remote URLs, returns the /vsicurl/ path directly.
        For S3 storage, downloads to a temporary file and yields the local path,
        unless never_return_local_file=True, in which case returns presigned URL.
        Use as an async context manager to ensure cleanup.

        Args:
            never_return_local_file: If True, return presigned URLs for S3 instead of downloading
        """

        from src.structures import async_conn
        from src.utils import get_async_s3_client, get_bucket_name

        @asynccontextmanager
        async def _source_context():
            if self.type == "postgis":
                if not self.postgis_connection_id or not self.postgis_query:
                    raise ValueError(
                        f"PostGIS layer {self.layer_id} missing connection_id or query"
                    )

                async with async_conn("get_ogr_source_postgis") as conn:
                    connection_result = await conn.fetchrow(
                        """
                        SELECT connection_uri FROM project_postgres_connections
                        WHERE id = $1
                        """,
                        self.postgis_connection_id,
                    )
                    if not connection_result:
                        raise ValueError(
                            f"PostGIS connection {self.postgis_connection_id} not found"
                        )

                    connection_uri = connection_result["connection_uri"]

                with tempfile.NamedTemporaryFile(
                    suffix=".gpkg", delete=True
                ) as temp_gpkg:
                    temp_gpkg_path = temp_gpkg.name

                try:
                    ogr_cmd = [
                        "ogr2ogr",
                        "-overwrite",
                        "-if",
                        "PostgreSQL",
                        "-f",
                        "GPKG",
                        temp_gpkg_path,
                        connection_uri,
                        "-sql",
                        self.postgis_query,
                    ]

                    process = await asyncio.create_subprocess_exec(
                        *ogr_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode != 0:
                        raise RuntimeError(f"ogr2ogr failed: {stderr.decode()}")

                    if never_return_local_file:
                        bucket_name = get_bucket_name()
                        s3_client = await get_async_s3_client()
                        timestamp = int(time.time())
                        s3_key = f"temp/postgis/{self.layer_id}_{timestamp}.gpkg"

                        await s3_client.upload_file(temp_gpkg_path, bucket_name, s3_key)

                        presigned_url = await s3_client.generate_presigned_url(
                            "get_object",
                            Params={"Bucket": bucket_name, "Key": s3_key},
                            ExpiresIn=900,  # 15 minutes
                        )

                        yield presigned_url
                    else:
                        yield temp_gpkg_path

                finally:
                    # clean up temporary file after context exits
                    if os.path.exists(temp_gpkg_path):
                        os.unlink(temp_gpkg_path)

            elif self.remote_url:
                # Special handling for WFS (Web Feature Service) URLs
                # WFS URLs contain service protocol parameters and should not use /vsicurl/ prefix
                if (
                    "SERVICE=WFS" in self.remote_url.upper()
                    and "REQUEST=GETFEATURE" in self.remote_url.upper()
                ):
                    yield f"WFS:{self.remote_url}"  # Use WFS driver prefix
                elif self.remote_url.startswith("CSV:/vsicurl/"):
                    # CSV URLs are already prefixed, use as-is
                    yield self.remote_url
                elif self.remote_url.startswith("ESRIJSON:"):
                    # ESRI Feature Service or Map Service URLs with ESRIJSON prefix
                    yield self.remote_url
                else:
                    # Regular remote URL: use vsicurl
                    yield f"/vsicurl/{self.remote_url}"
            elif self.s3_key:
                # S3 storage: either download to temp file or return presigned URL
                s3_client = await get_async_s3_client()
                bucket_name = get_bucket_name()

                if never_return_local_file:
                    # Generate presigned GET URL for remote access
                    presigned_url = await s3_client.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": bucket_name, "Key": self.s3_key},
                        ExpiresIn=3600,
                    )
                    yield presigned_url
                else:
                    # Download to temporary file for local access
                    file_ext = os.path.splitext(self.s3_key)[1] if self.s3_key else ""
                    with tempfile.NamedTemporaryFile(
                        suffix=file_ext, delete=False
                    ) as tmp:
                        temp_path = tmp.name

                    try:
                        # Download S3 file to temporary location
                        await s3_client.download_file(
                            bucket_name, self.s3_key, temp_path
                        )
                        yield temp_path
                    finally:
                        # Clean up temporary file
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
            else:
                raise ValueError(
                    f"Layer {self.layer_id} has no data source (no s3_key, remote_url, or postgis configuration)"
                )

        return _source_context()

    # Relationships
    postgis_connection = relationship(
        "ProjectPostgresConnection", back_populates="layers"
    )
    styles = relationship("LayerStyle", back_populates="layer")
    map_layer_styles = relationship("MapLayerStyle", back_populates="layer")


class LayerStyle(Base):
    __tablename__ = "layer_styles"

    style_id = Column(String(12), primary_key=True)  # starts with S
    layer_id = Column(String(12), ForeignKey("map_layers.layer_id"), nullable=False)
    style_json = Column(JSONB, nullable=False)  # MapLibre layers list
    parent_style_id = Column(
        String(12), ForeignKey("layer_styles.style_id")
    )  # NULL = first version
    created_by = Column(UUID, nullable=False)
    created_on = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    # Relationships
    layer = relationship("MapLayer", back_populates="styles")
    parent_style = relationship("LayerStyle", remote_side=[style_id])
    map_layer_styles = relationship("MapLayerStyle", back_populates="style")


class MapLayerStyle(Base):
    __tablename__ = "map_layer_styles"

    map_id = Column(String(12), ForeignKey("user_mundiai_maps.id"), primary_key=True)
    layer_id = Column(String(12), ForeignKey("map_layers.layer_id"), primary_key=True)
    style_id = Column(String(12), ForeignKey("layer_styles.style_id"), nullable=False)

    # Relationships
    map = relationship("MundiMap", back_populates="layer_styles")
    layer = relationship("MapLayer", back_populates="map_layer_styles")
    style = relationship("LayerStyle", back_populates="map_layer_styles")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    project_id = Column(
        String(12), ForeignKey("user_mundiai_projects.id"), nullable=False
    )
    owner_uuid = Column(UUID, nullable=False)
    title = Column(String)
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.current_timestamp()
    )
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=func.current_timestamp()
    )
    soft_deleted_at = Column(TIMESTAMP(timezone=True))

    # Relationships
    chat_completion_messages = relationship(
        "MundiChatCompletionMessage", back_populates="conversation"
    )


class MundiChatCompletionMessage(Base):
    __tablename__ = "chat_completion_messages"

    id: int = Column(Integer, primary_key=True)
    map_id: str = Column(String(12), ForeignKey("user_mundiai_maps.id"), nullable=False)
    conversation_id: int = Column(
        Integer, ForeignKey("conversations.id"), nullable=True
    )
    sender_id = Column(UUID, nullable=False)
    message_json: dict = Column(JSONB, nullable=False)
    created_at: datetime = Column(
        TIMESTAMP(timezone=True), server_default=func.current_timestamp()
    )

    # Relationships
    map = relationship("MundiMap", back_populates="chat_completion_messages")
    conversation = relationship(
        "Conversation", back_populates="chat_completion_messages"
    )
