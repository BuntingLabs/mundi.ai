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
from openai import BadRequestError


@pytest.fixture
def test_map_fixture(sync_auth_client):
    map_title = f"Test Context Length Error Map {uuid.uuid4()}"

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
async def test_websocket_context_length_exceeded_error(
    test_map_fixture, sync_auth_client, websocket_url_for_map
):
    """Test that context length exceeded error is properly handled and sent via websocket"""

    # Create the BadRequestError with the specific error format
    # Note: OpenAI library expects code/type/param at top level of body, not nested under 'error'
    error_body = {
        "message": "This model's maximum context length is 200000 tokens. However, your messages resulted in 311486 tokens (309560 in the messages, 1926 in the functions). Please reduce the length of the messages or functions.",
        "type": "invalid_request_error",
        "param": "messages",
        "code": "context_length_exceeded",
    }

    def mock_openai_error(*args, **kwargs):
        from unittest.mock import Mock

        response = Mock()
        response.request = Mock()
        response.status_code = 400
        response.headers = {"x-request-id": "test"}
        raise BadRequestError("Error code: 400", response=response, body=error_body)

    with patch("src.routes.message_routes.get_openai_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=mock_openai_error)
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
            # Send message that will trigger the error
            response = sync_auth_client.post(
                f"/api/maps/conversations/{conversation_id}/maps/{map_id}/send",
                json={
                    "message": {
                        "role": "user",
                        "content": "This should trigger context length exceeded error",
                    },
                    "selected_feature": None,
                },
            )
            assert response.status_code == 200

            # Receive messages until we get the error notification
            error_msg = None
            max_attempts = 10
            for _ in range(max_attempts):
                recv_msg = websocket.receive_json()
                if recv_msg.get("ephemeral") is True and "error_message" in recv_msg:
                    error_msg = recv_msg
                    break

            assert error_msg is not None, "Did not receive error notification message"
            assert "ephemeral" in error_msg
            assert error_msg["ephemeral"] is True
            assert "action_id" in error_msg
            assert "error_message" in error_msg
            assert (
                error_msg["error_message"]
                == "Maximum context length for LLM has been reached. Please create a new chat to continue using the chat feature."
            )
