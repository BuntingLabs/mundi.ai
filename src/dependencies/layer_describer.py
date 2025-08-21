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

import asyncpg
import csv
import fiona
import io
import json
import os
import tempfile
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Dict, Any, List

from src.utils import get_async_s3_client, get_bucket_name
from src.structures import get_async_db_connection


class LayerDescriber(ABC):
    @abstractmethod
    async def describe_layer(self, layer_id: str, layer_data: Dict[str, Any]) -> str:
        pass

    @abstractmethod
    async def describe_postgis_layer(self, layer_data: Dict[str, Any]) -> List[str]:
        pass

    @abstractmethod
    async def describe_raster_layer(self, layer_data: Dict[str, Any]) -> List[str]:
        pass

    @abstractmethod
    async def describe_point_cloud_layer(self, layer_data: Dict[str, Any]) -> List[str]:
        pass

    @abstractmethod
    async def describe_vector_layer(
        self, layer_id: str, layer_data: Dict[str, Any]
    ) -> List[str]:
        pass


class DefaultLayerDescriber(LayerDescriber):
    async def describe_layer(self, layer_id: str, layer_data: Dict[str, Any]) -> str:
        markdown_content = []
        markdown_content.append(f"# Layer: {layer_data['name']}\n")
        markdown_content.append(f"ID: {layer_id}")
        markdown_content.append(f"Type: {layer_data['type']}")

        if layer_data["type"] == "postgis":
            postgis_content = await self.describe_postgis_layer(layer_data)
            markdown_content.extend(postgis_content)
        elif layer_data["type"] == "raster":
            raster_content = await self.describe_raster_layer(layer_data)
            markdown_content.extend(raster_content)
        elif layer_data["type"] == "point_cloud":
            point_cloud_content = await self.describe_point_cloud_layer(layer_data)
            markdown_content.extend(point_cloud_content)
        else:
            vector_content = await self.describe_vector_layer(layer_id, layer_data)
            markdown_content.extend(vector_content)

        return "\n".join(markdown_content)

    async def describe_postgis_layer(self, layer_data: Dict[str, Any]) -> List[str]:
        markdown_content = []

        async with get_async_db_connection() as conn:
            connection_result = await conn.fetchrow(
                """
                SELECT ppc.connection_name, ppc.connection_uri, pps.friendly_name
                FROM project_postgres_connections ppc
                LEFT JOIN project_postgres_summary pps ON pps.connection_id = ppc.id
                WHERE ppc.id = $1
                """,
                layer_data.get("postgis_connection_id"),
            )
            if connection_result:
                connection_name = (
                    connection_result["friendly_name"]
                    or connection_result["connection_name"]
                    or "Loading..."
                )
                markdown_content.append(f"PostGIS Connection: {connection_name}")

                try:
                    geom_type_query = f"""
                    SELECT ST_GeometryType(geom) as geom_type, COUNT(*) as count
                    FROM ({layer_data.get("postgis_query", "SELECT NULL as geom")}) t
                    WHERE geom IS NOT NULL
                    GROUP BY ST_GeometryType(geom)
                    ORDER BY count DESC
                    """

                    async with asyncpg.connect(
                        connection_result["connection_uri"], ssl=True
                    ) as postgis_conn:
                        geom_results = await postgis_conn.fetch(geom_type_query)

                    if geom_results:
                        markdown_content.append("\n## Geometry Types\n")
                        for row in geom_results:
                            geom_type = row["geom_type"].replace("ST_", "")
                            markdown_content.append(
                                f"{geom_type}: {row['count']} features"
                            )

                except Exception as e:
                    markdown_content.append(
                        f"Geometry Type: Unable to analyze ({str(e)})"
                    )

        markdown_content.append(f"Query: {layer_data.get('postgis_query', '???')}")
        markdown_content.append(
            f"Created On: {str(layer_data['created_on']) if layer_data['created_on'] else 'Unknown'}"
        )
        markdown_content.append(
            f"Last Edited: {str(layer_data['last_edited']) if layer_data['last_edited'] else 'Unknown'}"
        )

        return markdown_content

    async def describe_raster_layer(self, layer_data: Dict[str, Any]) -> List[str]:
        markdown_content = []

        markdown_content.append(
            f"Created On: {str(layer_data['created_on']) if layer_data['created_on'] else 'Unknown'}"
        )
        markdown_content.append(
            f"Last Edited: {str(layer_data['last_edited']) if layer_data['last_edited'] else 'Unknown'}"
        )

        if layer_data["bounds"]:
            markdown_content.append("\n## Geographic Extent\n")
            markdown_content.append(
                f"Bounds (WGS84): {layer_data['bounds'][0]:.6f},{layer_data['bounds'][1]:.6f},{layer_data['bounds'][2]:.6f},{layer_data['bounds'][3]:.6f}"
            )

        if layer_data["metadata"]:
            # Parse metadata JSON if it's a string (asyncpg returns JSON as strings)
            metadata = layer_data["metadata"]
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}

            if metadata and "raster_value_stats_b1" in metadata:
                markdown_content.append("\n## Raster Statistics\n")
                min_val = metadata["raster_value_stats_b1"]["min"]
                max_val = metadata["raster_value_stats_b1"]["max"]
                markdown_content.append(f"Min Value: {min_val}")
                markdown_content.append(f"Max Value: {max_val}")

        return markdown_content

    async def describe_point_cloud_layer(self, layer_data: Dict[str, Any]) -> List[str]:
        markdown_content = []

        markdown_content.append(
            f"Created On: {str(layer_data['created_on']) if layer_data['created_on'] else 'Unknown'}"
        )
        markdown_content.append(
            f"Last Edited: {str(layer_data['last_edited']) if layer_data['last_edited'] else 'Unknown'}"
        )

        if layer_data["bounds"]:
            markdown_content.append("\n## Geographic Extent\n")
            markdown_content.append(
                f"Bounds (WGS84): {layer_data['bounds'][0]:.6f},{layer_data['bounds'][1]:.6f},{layer_data['bounds'][2]:.6f},{layer_data['bounds'][3]:.6f}"
            )

        if layer_data["metadata"]:
            # Parse metadata JSON if it's a string (asyncpg returns JSON as strings)
            metadata = layer_data["metadata"]
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}

        return markdown_content

    async def describe_vector_layer(
        self, layer_id: str, layer_data: Dict[str, Any]
    ) -> List[str]:
        markdown_content = []

        markdown_content.append(
            f"Geometry Type: {layer_data['geometry_type'] if layer_data['geometry_type'] else 'Unknown'}"
        )
        if layer_data["feature_count"] is not None:
            markdown_content.append(f"Feature Count: {layer_data['feature_count']}")
        markdown_content.append(
            f"Created On: {str(layer_data['created_on']) if layer_data['created_on'] else 'Unknown'}"
        )
        markdown_content.append(
            f"Last Edited: {str(layer_data['last_edited']) if layer_data['last_edited'] else 'Unknown'}"
        )

        # TODO: Add proper remote source description
        if layer_data.get("remote_url"):
            markdown_content.append("Source: Remote")
            return markdown_content

        bucket_name = get_bucket_name()

        with tempfile.TemporaryDirectory() as temp_dir:
            s3_key = layer_data["s3_key"]
            file_extension = os.path.splitext(s3_key)[1]

            local_input_file = os.path.join(
                temp_dir, f"layer_{layer_id}_input{file_extension}"
            )

            s3 = await get_async_s3_client()
            await s3.download_file(bucket_name, s3_key, local_input_file)

            with fiona.open(local_input_file) as src:
                feature_count = len(src)
                features = list(src)
                schema = src.schema
                crs = src.crs

                markdown_content.append("\n## Geographic Extent\n")
                if layer_data["bounds"]:
                    markdown_content.append(
                        f"Dataset Bounds: {layer_data['bounds'][0]:.6f},{layer_data['bounds'][1]:.6f},{layer_data['bounds'][2]:.6f},{layer_data['bounds'][3]:.6f}"
                    )

                markdown_content.append("\n## Schema Information\n")

                async with get_async_db_connection() as conn:
                    await conn.execute(
                        """
                        UPDATE map_layers
                        SET feature_count = $1
                        WHERE layer_id = $2
                        """,
                        feature_count,
                        layer_id,
                    )

                markdown_content.append(f"CRS: {crs.to_string() if crs else 'Unknown'}")
                markdown_content.append(f"Driver: {src.driver}")
                markdown_content.append("\n### Attribute Fields\n")

                if "properties" in schema and schema["properties"]:
                    fields_by_type = {}
                    for field_name, field_type in schema["properties"].items():
                        if field_type not in fields_by_type:
                            fields_by_type[field_type] = []
                        fields_by_type[field_type].append(field_name)

                    for field_type in sorted(fields_by_type.keys()):
                        markdown_content.append(f"\n#### {field_type}\n")
                        for field_name in sorted(fields_by_type[field_type]):
                            markdown_content.append(f"{field_name}")
                else:
                    markdown_content.append("No attribute fields found.")

                features_with_attrs = []
                for i, feature in enumerate(features[:10]):
                    features_with_attrs.append(feature["properties"])

                if features_with_attrs:
                    all_fieldnames = set()
                    for feature_props in features_with_attrs:
                        all_fieldnames.update(feature_props.keys())

                    fieldnames = sorted(list(all_fieldnames))

                    markdown_content.append("\n## Sampled Features Attribute Table\n")

                    markdown_content.append(
                        f"\nRandomly sampled {len(features_with_attrs)} of {feature_count} features for this table."
                    )

                    csv_output = io.StringIO()
                    writer = csv.DictWriter(csv_output, fieldnames=fieldnames)
                    writer.writeheader()

                    for feature_props in features_with_attrs:
                        filtered_props = {}
                        for k in fieldnames:
                            value = feature_props.get(k, "")
                            filtered_props[k] = value
                        writer.writerow(filtered_props)

                    markdown_content.append("```csv")
                    markdown_content.append(csv_output.getvalue())
                    markdown_content.append("```")

        return markdown_content


@lru_cache(maxsize=1)
def get_layer_describer() -> LayerDescriber:
    return DefaultLayerDescriber()
