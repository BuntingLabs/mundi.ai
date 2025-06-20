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

from __future__ import annotations
import os
from psycopg2 import pool
import asyncpg
from typing import Optional

_connection_pool = None
_async_connection_pool = None


def _get_connection_pool():
    global _connection_pool
    if _connection_pool is None:
        # Construct URL from components
        user = os.environ["POSTGRES_USER"]
        password = os.environ["POSTGRES_PASSWORD"]
        host = os.environ["POSTGRES_HOST"]
        port = os.environ.get("POSTGRES_PORT", "5432")
        db = os.environ["POSTGRES_DB"]
        postgres_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=postgres_url,
        )
    return _connection_pool


async def _get_async_connection_pool():
    global _async_connection_pool
    if _async_connection_pool is None:
        # Construct URL from components
        user = os.environ["POSTGRES_USER"]
        password = os.environ["POSTGRES_PASSWORD"]
        host = os.environ["POSTGRES_HOST"]
        port = os.environ.get("POSTGRES_PORT", "5432")
        db = os.environ["POSTGRES_DB"]
        postgres_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
        _async_connection_pool = await asyncpg.create_pool(
            dsn=postgres_url,
            min_size=1,
            max_size=10,
        )
    return _async_connection_pool


class DatabaseConnection:
    def __init__(self):
        self.conn = None

    def __enter__(self):
        pool = _get_connection_pool()
        self.conn = pool.getconn()
        self.conn.autocommit = True
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            pool = _get_connection_pool()
            pool.putconn(self.conn)


class AsyncDatabaseConnection:
    """Context-manager that yields an *exclusive* connection.

    Using a per-request dedicated connection completely avoids the
    "another operation is in progress" race that can occur when the same
    connection object is shared between overlapping coroutines.  The
    overhead of opening a new connection is negligible for the test
    suite and greatly simplifies correctness.
    """

    def __init__(self):
        self.conn: Optional[asyncpg.Connection] = None

    async def __aenter__(self) -> asyncpg.Connection:
        # Construct URL from components
        user = os.environ["POSTGRES_USER"]
        password = os.environ["POSTGRES_PASSWORD"]
        host = os.environ["POSTGRES_HOST"]
        port = os.environ.get("POSTGRES_PORT", "5432")
        db = os.environ["POSTGRES_DB"]
        postgres_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
        # Create a brand-new connection so that no other coroutine can
        # possibly be using it concurrently.
        self.conn = await asyncpg.connect(dsn=postgres_url)
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.conn is not None:
            await self.conn.close()


def get_db_connection():
    return DatabaseConnection()


def get_async_db_connection():
    return AsyncDatabaseConnection()
