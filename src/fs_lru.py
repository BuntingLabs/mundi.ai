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
from collections import OrderedDict
import asyncio
from contextlib import asynccontextmanager
from src.structures import get_async_db_connection
from src.utils import get_async_s3_client, get_bucket_name


class FileCache:
    def __init__(self, cache_dir, max_size):
        os.makedirs(cache_dir, exist_ok=True)
        self.cache_dir, self.max_size = cache_dir, max_size
        self.cache = OrderedDict()  # key -> file size
        self.locked_keys = set()
        self.total = 0
        for fn in os.listdir(cache_dir):
            path = os.path.join(cache_dir, fn)
            size = os.path.getsize(path)
            self.cache[fn] = size
            self.total += size

    def _evict(self):
        while self.total > self.max_size:
            for key in list(self.cache.keys()):
                if key not in self.locked_keys:
                    size = self.cache.pop(key)
                    os.remove(os.path.join(self.cache_dir, key))
                    self.total -= size
                    break
            else:
                break

    def set(self, key, data: bytes):
        path = os.path.join(self.cache_dir, key)
        with open(path, "wb") as f:
            f.write(data)
        size = os.path.getsize(path)
        if key in self.cache:
            self.total -= self.cache.pop(key)
        self.cache[key] = size
        self.total += size
        self._evict()

    def get(self, key) -> bytes:
        if key not in self.cache:
            raise KeyError(f"Key {key} not found in cache")
        path = os.path.join(self.cache_dir, key)
        self.cache.move_to_end(key)
        with open(path, "rb") as f:
            return f.read()

    def has(self, key) -> bool:
        return key in self.cache

    def get_path(self, key) -> str:
        if key not in self.cache:
            raise KeyError(f"Key {key} not found in cache")
        self.cache.move_to_end(key)
        return os.path.join(self.cache_dir, key)

    def lock(self, key):
        self.locked_keys.add(key)

    def unlock(self, key):
        self.locked_keys.discard(key)


class LayerCache:
    def __init__(self):
        self.file_cache = FileCache(
            cache_dir="/cache", max_size=1024 * 1024 * 128
        )  # 128 MiB

    @asynccontextmanager
    async def layer_filename(self, layer_id: str):
        cache_key = f"{layer_id}.gpkg"

        await self.bytes_for_layer(layer_id, "GeoPackage")

        self.file_cache.lock(cache_key)
        try:
            yield self.file_cache.get_path(cache_key)
        finally:
            self.file_cache.unlock(cache_key)

    async def bytes_for_layer(self, layer_id: str, format: str = "GeoPackage") -> bytes:
        cache_key = f"{layer_id}.gpkg"

        try:
            return self.file_cache.get(cache_key)
        except (KeyError, FileNotFoundError):
            # not cached yet or missing file, proceed to fetch
            pass

        async with get_async_db_connection() as conn:
            layer = await conn.fetchrow(
                """
                SELECT layer_id, name, type, metadata, bounds, geometry_type,
                    created_on, last_edited, feature_count, s3_key, remote_url
                FROM map_layers
                WHERE layer_id = $1
                """,
                layer_id,
            )

            if not layer:
                raise KeyError(f"Layer {layer_id} not found")

            if layer["type"] == "postgis":
                raise KeyError(
                    f"PostGIS layer {layer_id} cannot be pulled as individual vector file"
                )

            # Check if the layer is associated with any maps via the layers array
            # Order by created_on DESC to get the most recently created map first
            await conn.fetch(
                """
                SELECT id, title, description, owner_uuid
                FROM user_mundiai_maps
                WHERE $1 = ANY(layers) AND soft_deleted_at IS NULL
                ORDER BY created_on DESC
                """,
                layer_id,
            )

            # Handle remote sources
            if layer["remote_url"]:
                # Remote URL: use vsicurl with ogr2ogr
                ogr_source = f"/vsicurl/{layer['remote_url']}"

                with tempfile.TemporaryDirectory() as temp_dir:
                    cached_output_gpkg = os.path.join(temp_dir, f"{layer_id}.gpkg")

                    if format != "GeoPackage":
                        raise TypeError("only GeoPackage supported in bytes_for_layer")

                    # Use ogr2ogr to convert remote source to GPKG
                    ogr_cmd = [
                        "ogr2ogr",
                        "-f",
                        "GPKG",
                        cached_output_gpkg,
                        ogr_source,
                    ]
                    process = await asyncio.create_subprocess_exec(*ogr_cmd)
                    await process.wait()
                    if process.returncode != 0:
                        raise Exception(
                            f"ogr2ogr command failed with exit code {process.returncode}"
                        )

                    with open(cached_output_gpkg, "rb") as f:
                        data = f.read()
                    self.file_cache.set(cache_key, data)

            else:
                # S3 storage: original approach
                bucket_name = get_bucket_name()

                with tempfile.TemporaryDirectory() as temp_dir:
                    s3_key = layer["s3_key"]
                    file_extension = os.path.splitext(s3_key)[1]

                    local_input_file = os.path.join(
                        temp_dir, f"{layer_id}_input{file_extension}"
                    )

                    s3 = await get_async_s3_client()
                    await s3.download_file(bucket_name, s3_key, local_input_file)

                    cached_output_gpkg = os.path.join(temp_dir, f"{layer_id}.gpkg")

                    if format != "GeoPackage":
                        raise TypeError("only GeoPackage supported in bytes_for_layer")

                    if file_extension.lower() == ".gpkg":
                        with (
                            open(local_input_file, "rb") as src,
                            open(cached_output_gpkg, "wb") as dst,
                        ):
                            dst.write(src.read())
                    else:
                        ogr_cmd = [
                            "ogr2ogr",
                            "-f",
                            "GPKG",
                            cached_output_gpkg,
                            local_input_file,
                        ]
                        process = await asyncio.create_subprocess_exec(*ogr_cmd)
                        await process.wait()
                        if process.returncode != 0:
                            raise Exception(
                                f"ogr2ogr command failed with exit code {process.returncode}"
                            )

                    with open(cached_output_gpkg, "rb") as f:
                        data = f.read()
                    self.file_cache.set(cache_key, data)

        return self.file_cache.get(cache_key)


cache_singleton = LayerCache()


def layer_cache() -> LayerCache:
    return cache_singleton
