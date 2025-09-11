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
import json
from unittest.mock import patch, AsyncMock
from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionMessageToolCall,
)
from openai.types.chat.chat_completion_message_tool_call import Function


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
    map_title = f"Test Zoom Integration Map {uuid.uuid4()}"

    response = sync_auth_client.post(
        "/api/maps/create",
        json={
            "title": map_title,
            "link_accessible": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    return {"map_id": data["id"], "project_id": data["project_id"]}


@pytest.mark.anyio
async def test_zoom_integration_with_real_openai(
    auth_client, test_map_fixture, sync_auth_client, websocket_url_for_map
):
    def create_response_queue():
        return [
            MockResponse(
                "I'll zoom to downtown Seattle for you.",
                [
                    ChatCompletionMessageToolCall(
                        id="call_1",
                        type="function",
                        function=Function(
                            name="zoom_to_bounds",
                            arguments=json.dumps(
                                {
                                    "bounds": [-122.4194, 47.6062, -122.3320, 47.6205],
                                    "zoom_description": "Zooming to downtown Seattle",
                                }
                            ),
                        ),
                    )
                ],
            ),
            MockResponse(
                "I've zoomed to downtown Seattle for you. The map should now show the area with bounds [-122.4194, 47.6062, -122.3320, 47.6205].",
                None,
            ),
        ]

    response_queue = create_response_queue()

    with patch("src.routes.message_routes.get_openai_client") as mock_get_client:
        mock_client = AsyncMock()

        async def mock_create(*args, **kwargs):
            response = response_queue.pop(0)
            return response

        mock_client.chat.completions.create = AsyncMock(side_effect=mock_create)
        mock_get_client.return_value = mock_client

        map_id = test_map_fixture["map_id"]
        project_id = test_map_fixture["project_id"]

        # Create conversation
        response = sync_auth_client.post(
            "/api/conversations",
            json={"project_id": project_id},
        )
        assert response.status_code == 200
        conversation_id = response.json()["id"]

        with sync_auth_client.websocket_connect(
            websocket_url_for_map(map_id, conversation_id)
        ) as websocket:
            response = sync_auth_client.post(
                f"/api/maps/conversations/{conversation_id}/maps/{map_id}/send",
                json={
                    "message": {
                        "role": "user",
                        "content": "Please zoom to downtown Seattle with bounds [-122.4194, 47.6062, -122.3320, 47.6205]",
                    },
                    "selected_feature": None,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "processing_started"
            assert "message_id" in data

            # our own message
            sent_msg = websocket.receive_json()
            assert sent_msg["role"] == "user"
            assert "zoom to downtown Seattle" in sent_msg["content"]

            # Kue is thinking
            msg = websocket.receive_json()
            assert msg["ephemeral"] and msg["action"] == "Kue is thinking..."
            msg = websocket.receive_json()
            assert msg["ephemeral"] and msg["action"] == "Kue is thinking..."
            assert msg["status"] == "completed"

            # Message 4: Zoom action (start)
            msg4 = websocket.receive_json()
            # Message 4: Assistant message with tool call
            assert msg4["role"] == "assistant"
            assert msg4["content"] == "I'll zoom to downtown Seattle for you."
            assert msg4["has_tool_calls"]
            assert len(msg4["tool_calls"]) == 1
            assert msg4["tool_calls"][0]["id"] == "call_1"

            # Message 5: Zoom action (start)
            msg5 = websocket.receive_json()
            assert msg5["ephemeral"]
            assert "Zooming to downtown Seattle" in msg5["action"]
            assert "bounds" in msg5
            assert msg5["bounds"] == [-122.4194, 47.6062, -122.332, 47.6205]
            assert msg5["status"] == "active"

            # Message 6: Zoom action (completed)
            msg6 = websocket.receive_json()
            assert msg6["ephemeral"]
            assert "Zooming to downtown Seattle" in msg6["action"]
            assert msg6["status"] == "completed"

            # Tool response message after zoom action completes
            msg6_tool = websocket.receive_json()
            assert msg6_tool["role"] == "tool"
            assert msg6_tool["tool_response"]["id"] == "call_1"
            assert msg6_tool["tool_response"]["status"] == "success"

            # Message 7: Final thinking (start)
            msg7 = websocket.receive_json()
            assert msg7["ephemeral"]
            assert msg7["action"] == "Kue is thinking..."
            assert msg7["status"] == "active"

            # Message 8: Final thinking (completed)
            msg8 = websocket.receive_json()
            assert msg8["ephemeral"]
            assert msg8["action"] == "Kue is thinking..."
            assert msg8["status"] == "completed"

            # Message 9: Final assistant response
            msg9 = websocket.receive_json()
            assert msg9["role"] == "assistant"
            assert "zoomed to downtown Seattle" in msg9["content"]
