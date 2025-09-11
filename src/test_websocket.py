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
import time
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
    map_title = f"Test WebSocket Map {uuid.uuid4()}"

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


def test_websocket_successful_connection(
    test_map_fixture, sync_auth_client, websocket_url_for_map
):
    map_id = test_map_fixture["map_id"]
    project_id = test_map_fixture["project_id"]

    # Create conversation
    response = sync_auth_client.post(
        "/api/conversations",
        json={"project_id": project_id},
    )
    assert response.status_code == 200
    conversation_id = response.json()["id"]

    # no errors
    with sync_auth_client.websocket_connect(
        websocket_url_for_map(map_id, conversation_id)
    ):
        pass


def test_websocket_404(sync_auth_client):
    test_map_id = "should-404-doesntexist"

    with pytest.raises(Exception):  # TestClient raises different exceptions
        with sync_auth_client.websocket_connect(
            f"/api/maps/ws/{test_map_id}/messages/updates"
        ):
            pytest.fail("WebSocket connection should have failed without token")


def test_websocket_receive_ephemeral_action(
    test_map_fixture, sync_auth_client, websocket_url_for_map
):
    def create_response_queue():
        return [
            MockResponse("Hello! How can I help?", None),
        ]

    response_queue = create_response_queue()

    with patch("src.routes.message_routes.get_openai_client") as mock_get_client:
        mock_client = AsyncMock()

        async def mock_create(*args, **kwargs):
            return response_queue.pop(0)

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
                        "content": "Hello",
                    },
                    "selected_feature": None,
                },
            )
            assert response.status_code == 200

            # Receive messages until we get the ephemeral action message
            ephemeral_msg = None
            max_attempts = 10
            for _ in range(max_attempts):
                recv_msg = websocket.receive_json()
                if recv_msg.get("ephemeral") is True:
                    ephemeral_msg = recv_msg
                    break

            assert ephemeral_msg is not None, "Did not receive ephemeral action message"
            assert "ephemeral" in ephemeral_msg
            assert ephemeral_msg["ephemeral"] is True
            assert "action_id" in ephemeral_msg
            assert "action" in ephemeral_msg
            assert "timestamp" in ephemeral_msg
            assert "status" in ephemeral_msg


def test_websocket_missed_messages(
    test_map_fixture, sync_auth_client, websocket_url_for_map
):
    def create_response_queue():
        return [
            MockResponse("Hello! How can I help?", None),
            MockResponse("Hello again! How can I assist?", None),
        ]

    response_queue = create_response_queue()

    with patch("src.routes.message_routes.get_openai_client") as mock_get_client:
        mock_client = AsyncMock()

        async def mock_create(*args, **kwargs):
            return response_queue.pop(0)

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
                        "content": "Hello",
                    },
                    "selected_feature": None,
                },
            )
            assert response.status_code == 200

            # Receive messages until we get the ephemeral action message
            ephemeral_msg = None
            max_attempts = 10
            for _ in range(max_attempts):
                recv_msg = websocket.receive_json()
                if recv_msg.get("ephemeral") is True:
                    ephemeral_msg = recv_msg
                    break

            assert ephemeral_msg is not None, "Did not receive ephemeral action message"
            assert "ephemeral" in ephemeral_msg
            assert ephemeral_msg["ephemeral"] is True
            assert "action_id" in ephemeral_msg
            assert "action" in ephemeral_msg
            assert "timestamp" in ephemeral_msg
            assert "status" in ephemeral_msg

        response2 = sync_auth_client.post(
            f"/api/maps/conversations/{conversation_id}/maps/{map_id}/send",
            json={
                "message": {
                    "role": "user",
                    "content": "Hello again",
                },
                "selected_feature": None,
            },
        )
        assert response2.status_code == 200

        time.sleep(1)

        with sync_auth_client.websocket_connect(
            websocket_url_for_map(map_id, conversation_id)
        ) as websocket2:
            # Receive messages until we get the ephemeral action message
            ephemeral_msg = None
            max_attempts = 10
            for _ in range(max_attempts):
                recv_msg = websocket2.receive_json()
                if recv_msg.get("ephemeral") is True:
                    ephemeral_msg = recv_msg
                    break

            assert ephemeral_msg is not None, "Did not receive ephemeral action message"
            assert "ephemeral" in ephemeral_msg
            assert ephemeral_msg["ephemeral"] is True
            assert "action_id" in ephemeral_msg
            assert "action" in ephemeral_msg
            assert "timestamp" in ephemeral_msg
            assert "status" in ephemeral_msg
