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

import pytest
import uuid
from unittest.mock import patch, AsyncMock
from openai.types.chat import (
    ChatCompletionMessage,
)


class MockChoice:
    def __init__(self, content: str, tool_calls=None):
        self.message = ChatCompletionMessage(
            content=content, tool_calls=tool_calls, role="assistant"
        )


class MockResponse:
    def __init__(self, content: str, tool_calls=None):
        self.choices = [MockChoice(content, tool_calls)]


@pytest.fixture
def test_map_fixture(sync_auth_client):
    # Create a map with a project embedded
    response = sync_auth_client.post(
        "/api/maps/create",
        json={
            "title": f"Test Message Map {uuid.uuid4()}",
            "link_accessible": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    map_id = data["id"]
    project_id = data["project_id"]

    return {"map_id": map_id, "project_id": project_id}


@pytest.mark.anyio
async def test_send_and_get_messages(
    test_map_fixture, sync_auth_client, websocket_url_for_map
):
    map_id = test_map_fixture["map_id"]
    project_id = test_map_fixture["project_id"]

    def create_response_queue():
        return [
            MockResponse(
                "I'll help analyze your map.",
                None,
            ),
        ]

    response_queue = create_response_queue()

    with patch("src.routes.message_routes.get_openai_client") as mock_get_client:
        mock_client = AsyncMock()

        async def mock_create(*args, **kwargs):
            return response_queue.pop(0)

        mock_client.chat.completions.create = AsyncMock(side_effect=mock_create)
        mock_get_client.return_value = mock_client

        # Create a conversation
        conversation_response = sync_auth_client.post(
            "/api/conversations",
            json={"project_id": project_id},
        )
        assert conversation_response.status_code == 200
        conversation_id = conversation_response.json()["id"]

        response = sync_auth_client.get(
            f"/api/conversations/{conversation_id}/messages"
        )
        assert response.status_code == 200
        messages = response.json()
        assert isinstance(messages, list)
        assert len(messages) == 0

        with sync_auth_client.websocket_connect(
            websocket_url_for_map(map_id, conversation_id)
        ) as websocket:
            response = sync_auth_client.post(
                f"/api/maps/conversations/{conversation_id}/maps/{map_id}/send",
                json={
                    "message": {
                        "role": "user",
                        "content": "Hello, can you help me analyze this map?",
                    },
                    "selected_feature": None,
                },
            )
            assert response.status_code == 200
            assert response.json()["status"] == "processing_started"

            sent_msg = websocket.receive_json()
            assert sent_msg["role"] == "user"
            assert "analyze this map" in sent_msg["content"]
            assert not sent_msg["has_tool_calls"]
            assert sent_msg["conversation_id"] == conversation_id

            msg = websocket.receive_json()
            assert msg["ephemeral"] and msg["action"] == "Kue is thinking..."
            msg = websocket.receive_json()
            assert (
                msg["ephemeral"]
                and msg["action"] == "Kue is thinking..."
                and msg["status"] == "completed"
            )

            assistant_msg = websocket.receive_json()
            assert assistant_msg["role"] == "assistant"
            assert "analyze" in assistant_msg["content"]
            assert assistant_msg["conversation_id"] == conversation_id

        response = sync_auth_client.get(
            f"/api/conversations/{conversation_id}/messages"
        )
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) == 2
        # Messages are returned in flat structure from conversation endpoint
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
