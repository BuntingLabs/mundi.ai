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
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.dependencies.database_documenter import (
    DefaultDatabaseDocumenter,
    generate_id,
    get_database_documenter,
)


class MockAsyncContextManager:
    """Simple mock async context manager."""
    def __init__(self, conn):
        self.conn = conn
    
    async def __aenter__(self):
        return self.conn
    
    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.anyio
class TestDatabaseDocumenter:
    """Test suite for the DatabaseDocumenter functionality."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        with patch("src.dependencies.database_documenter.redis") as mock_redis:
            mock_redis.set = MagicMock()
            mock_redis.incr = MagicMock()
            yield mock_redis

    @pytest.fixture
    def mock_postgres_connection(self):
        """Mock PostgreSQL connection with sample data."""
        mock_conn = AsyncMock()
        
        # Mock table query response
        mock_conn.fetch.side_effect = [
            [{"table_name": "users"}, {"table_name": "orders"}],  # Tables query
            [  # Columns for users table
                {
                    "column_name": "id",
                    "data_type": "integer",
                    "is_nullable": "NO",
                    "column_default": None,
                },
                {
                    "column_name": "name",
                    "data_type": "text",
                    "is_nullable": "YES",
                    "column_default": None,
                },
            ],
            [  # Columns for orders table
                {
                    "column_name": "order_id",
                    "data_type": "integer",
                    "is_nullable": "NO",
                    "column_default": None,
                },
                {
                    "column_name": "user_id",
                    "data_type": "integer",
                    "is_nullable": "NO",
                    "column_default": None,
                },
            ],
        ]
        
        return mock_conn

    @pytest.fixture
    def mock_connection_manager(self, mock_postgres_connection):
        """Mock PostgresConnectionManager."""
        mock_manager = AsyncMock()
        mock_manager.connect_to_postgres.return_value = mock_postgres_connection
        return mock_manager

    @pytest.fixture
    def mock_openai_client(self):
        """Mock OpenAI client with controlled responses."""
        mock_client = AsyncMock()
        mock_completion = MagicMock()
        
        # Mock the response structure
        mock_message = MagicMock()
        mock_message.content = "Test Database"
        
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion
        
        return mock_client

    @pytest.fixture
    def mock_db_connection(self):
        """Mock database connection for summary storage."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        return mock_conn

    def test_generate_id(self):
        """Test the generate_id function."""
        # Test basic functionality
        id1 = generate_id()
        assert len(id1) == 12
        assert not id1.startswith("S")
        
        # Test with prefix
        id2 = generate_id(prefix="S")
        assert len(id2) == 12
        assert id2.startswith("S")
        
        # Test length parameter
        id3 = generate_id(length=8)
        assert len(id3) == 8
        
        # Test prefix validation
        with pytest.raises(AssertionError):
            generate_id(prefix="AB")  # More than 1 character

    def test_get_database_documenter(self):
        """Test the get_database_documenter factory function."""
        documenter = get_database_documenter()
        assert isinstance(documenter, DefaultDatabaseDocumenter)
        
        # Test caching (should return same instance)
        documenter2 = get_database_documenter()
        assert documenter is documenter2

    async def test_generate_documentation_success(
        self,
        mock_redis,
        mock_connection_manager,
        mock_openai_client,
        mock_db_connection,
    ):
        """Test successful documentation generation."""
        with patch("src.dependencies.database_documenter.get_async_db_connection") as mock_get_conn:
            mock_get_conn.return_value = MockAsyncContextManager(mock_db_connection)
            
            documenter = DefaultDatabaseDocumenter()
            
            friendly_name, documentation = await documenter.generate_documentation(
                connection_id="test_conn_123",
                connection_uri="postgresql://test:test@localhost:5432/testdb",
                connection_name="Test Database",
                connection_manager=mock_connection_manager,
                openai_client=mock_openai_client,
            )
            
            # Verify return values
            assert friendly_name == "Test Database"
            assert documentation is not None
            
            # Verify Redis calls
            mock_redis.set.assert_any_call("dbdocumenter:test_conn_123:total_tables", 2)
            mock_redis.set.assert_any_call("dbdocumenter:test_conn_123:processed_tables", 0)
            assert mock_redis.incr.call_count == 2  # Called for each table
            
            # Verify OpenAI calls (should be called twice: once for name, once for docs)
            assert mock_openai_client.chat.completions.create.call_count == 2
            
            # Verify database insert
            mock_db_connection.execute.assert_called_once()
            call_args = mock_db_connection.execute.call_args
            assert "INSERT INTO project_postgres_summary" in call_args[0][0]
            
            # Verify connection was closed
            mock_connection_manager.connect_to_postgres.return_value.close.assert_called_once()

    async def test_generate_documentation_connection_error(
        self, mock_redis, mock_connection_manager, mock_openai_client
    ):
        """Test documentation generation when connection fails."""
        # Mock connection failure
        mock_connection_manager.connect_to_postgres.side_effect = Exception("Connection failed")
        
        documenter = DefaultDatabaseDocumenter()
        
        friendly_name, documentation = await documenter.generate_documentation(
            connection_id="test_conn_123",
            connection_uri="postgresql://test:test@localhost:5432/testdb",
            connection_name="Test Database",
            connection_manager=mock_connection_manager,
            openai_client=mock_openai_client,
        )
        
        # Should return None, None on error (as per the code)
        assert friendly_name is None
        assert documentation is None
        
        # No Redis calls should be made
        mock_redis.set.assert_not_called()
        mock_redis.incr.assert_not_called()

    async def test_generate_documentation_empty_database(
        self,
        mock_redis,
        mock_connection_manager,
        mock_openai_client,
        mock_db_connection,
    ):
        """Test documentation generation for empty database."""
        # Mock empty database
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []  # No tables
        mock_connection_manager.connect_to_postgres.return_value = mock_conn
        
        with patch("src.dependencies.database_documenter.get_async_db_connection") as mock_get_conn:
            mock_get_conn.return_value = MockAsyncContextManager(mock_db_connection)
            
            documenter = DefaultDatabaseDocumenter()
            
            friendly_name, documentation = await documenter.generate_documentation(
                connection_id="test_conn_123",
                connection_uri="postgresql://test:test@localhost:5432/testdb",
                connection_name="Empty Database",
                connection_manager=mock_connection_manager,
                openai_client=mock_openai_client,
            )
            
            # Should still work with empty database
            assert friendly_name == "Test Database"
            assert documentation is not None
            
            # Verify Redis calls for empty database
            mock_redis.set.assert_any_call("dbdocumenter:test_conn_123:total_tables", 0)
            mock_redis.set.assert_any_call("dbdocumenter:test_conn_123:processed_tables", 0)

    async def test_generate_documentation_openai_error(
        self,
        mock_redis,
        mock_connection_manager,
        mock_openai_client,
        mock_db_connection,
    ):
        """Test documentation generation when OpenAI API fails."""
        with patch("src.dependencies.database_documenter.get_async_db_connection") as mock_get_conn:
            mock_get_conn.return_value = MockAsyncContextManager(mock_db_connection)
            
            # Mock OpenAI failure
            mock_openai_client.chat.completions.create.side_effect = Exception("API Error")
            
            documenter = DefaultDatabaseDocumenter()
            
            friendly_name, documentation = await documenter.generate_documentation(
                connection_id="test_conn_123",
                connection_uri="postgresql://test:test@localhost:5432/testdb",
                connection_name="Test Database",
                connection_manager=mock_connection_manager,
                openai_client=mock_openai_client,
            )
            
            # Should return None, None on error
            assert friendly_name is None
            assert documentation is None

    def test_database_documenter_abstract_class(self):
        """Test that DatabaseDocumenter is properly abstract."""
        from src.dependencies.database_documenter import DatabaseDocumenter
        
        # Should not be able to instantiate abstract class
        with pytest.raises(TypeError):
            DatabaseDocumenter()