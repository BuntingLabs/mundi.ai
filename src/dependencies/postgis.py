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
from abc import ABC, abstractmethod
from functools import lru_cache
from src.dependencies.postgres_connection import PostgresConnectionManager
from redis import Redis

redis = Redis(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    decode_responses=True,
)


class PostGISProvider(ABC):
    @abstractmethod
    async def get_tables_by_connection_id(
        self, connection_id: str, connection_manager: PostgresConnectionManager
    ) -> str:
        pass


class DefaultPostGISProvider(PostGISProvider):
    async def get_tables_by_connection_id(
        self, connection_id: str, connection_manager: PostgresConnectionManager
    ) -> str:
        cache_key = f"postgis:{connection_id}:tables"
        cached_result = redis.get(cache_key)
        if cached_result:
            return cached_result

        postgres_conn = await connection_manager.connect_to_postgres(connection_id)
        try:
            tables = await postgres_conn.fetch("""
                SELECT
                    t.table_name,
                    t.table_schema
                FROM information_schema.tables t
                WHERE t.table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                AND t.table_type = 'BASE TABLE'
                ORDER BY t.table_schema, t.table_name
            """)

            result = str([dict(table) for table in tables])

            redis.setex(cache_key, 3600, result)

            return result
        finally:
            await postgres_conn.close()


@lru_cache(maxsize=1)
def get_postgis_provider() -> PostGISProvider:
    return DefaultPostGISProvider()
