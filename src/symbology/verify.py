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

import asyncio
import tempfile
import os
import json

from src.dependencies.base_map import BaseMapProvider
from src.database.models import MapLayer


class StyleValidationError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


async def verify_full_style_json_str(style_json_str: str) -> bool:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as temp_file:
        temp_path = temp_file.name
        temp_file.write(style_json_str.encode("utf-8"))
        temp_file.flush()

    try:
        process = await asyncio.create_subprocess_exec(
            "gl-style-validate",
            temp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise StyleValidationError(stdout.decode("utf-8"))

        return True
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


async def verify_style_json_str(
    layers_str: str,
    base_map: BaseMapProvider,
    layer: MapLayer,
) -> bool:
    try:
        layers = json.loads(layers_str)
    except json.JSONDecodeError as e:
        raise StyleValidationError(f"Invalid JSON: {e}")

    if not isinstance(layers, list):
        raise StyleValidationError("Expected layers to be a JSON array")

    for layer_obj in layers:
        if not isinstance(layer_obj, dict):
            raise StyleValidationError(
                f"Expected layer object to be a dict, got {type(layer_obj)}"
            )

        layer_obj["source-layer"] = "reprojectedfgb"

        if layer_obj.get("source") != layer.layer_id:
            raise StyleValidationError(f"Layer source must be '{layer.layer_id}'")

    from src.routes.postgres_routes import get_map_style_internal

    style_json = await get_map_style_internal(
        map_id=layer.source_map_id,
        base_map=base_map,
        only_show_inline_sources=True,
        override_layers=json.dumps({layer.layer_id: layers}),
    )

    await verify_full_style_json_str(json.dumps(style_json))

    return True
