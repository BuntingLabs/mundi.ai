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
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
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
def test_map_with_layer_and_conversation(sync_auth_client):
    map_response = sync_auth_client.post(
        "/api/maps/create",
        json={
            "title": "Chat Completion Style Test Map",
        },
    )
    assert map_response.status_code == 200
    map_id = map_response.json()["id"]

    file_path = str(
        Path(__file__).parent.parent.parent / "test_fixtures" / "coho_range.gpkg"
    )
    with open(file_path, "rb") as f:
        layer_response = sync_auth_client.post(
            f"/api/maps/{map_id}/layers",
            files={"file": ("coho_range.gpkg", f, "application/octet-stream")},
            data={"layer_name": "Coho Salmon Range"},
        )
        assert layer_response.status_code == 200
        layer_data = layer_response.json()
        layer_id = layer_data["id"]
        child_map_id = layer_data["dag_child_map_id"]

    map_detail_response = sync_auth_client.get(f"/api/maps/{child_map_id}")
    assert map_detail_response.status_code == 200
    project_id = map_detail_response.json()["project_id"]

    conversation_response = sync_auth_client.post(
        "/api/conversations", json={"project_id": project_id}
    )
    assert conversation_response.status_code == 200
    conversation_id = conversation_response.json()["id"]

    return {
        "map_id": map_id,
        "child_map_id": child_map_id,
        "layer_id": layer_id,
        "conversation_id": conversation_id,
    }


@pytest.mark.anyio
async def test_set_layer_style_via_chat_completion(
    auth_client,
    test_map_with_layer_and_conversation,
    sync_auth_client,
    websocket_url_for_map,
):
    test_data = test_map_with_layer_and_conversation
    layer_id = test_data["layer_id"]
    child_map_id = test_data["child_map_id"]
    conversation_id = test_data["conversation_id"]

    test_fill_color = "#FF5733"
    test_stroke_color = "#2E86AB"
    test_fill_opacity = 0.69

    maplibre_layers = [
        {
            "id": f"{layer_id}-fill",
            "type": "fill",
            "source": layer_id,
            "paint": {
                "fill-color": test_fill_color,
                "fill-opacity": test_fill_opacity,
                "fill-outline-color": test_stroke_color,
            },
            "metadata": {"foo": "bar"},
        }
    ]

    response_queue = [
        MockResponse(
            "I'll apply a custom style to your layer with the specified colors.",
            [
                ChatCompletionMessageToolCall(
                    id="call_test123",
                    type="function",
                    function=Function(
                        name="set_layer_style",
                        arguments=json.dumps(
                            {
                                "layer_id": layer_id,
                                "maplibre_json_layers_str": json.dumps(maplibre_layers),
                            }
                        ),
                    ),
                )
            ],
        ),
        MockResponse(
            "I've applied a custom style to your layer with the specified colors.",
            None,
        ),
    ]

    with patch("src.routes.message_routes.get_openai_client") as mock_get_client:
        mock_client = AsyncMock()

        async def mock_create(*args, **kwargs):
            return response_queue.pop(0)

        mock_client.chat.completions.create = AsyncMock(side_effect=mock_create)
        mock_get_client.return_value = mock_client

        message_payload = {
            "message": {
                "role": "user",
                "content": f"Please style layer {layer_id} with custom colors",
            },
            "selected_feature": None,
        }

        with sync_auth_client.websocket_connect(
            websocket_url_for_map(child_map_id, conversation_id)
        ) as websocket:
            response = sync_auth_client.post(
                f"/api/maps/conversations/{conversation_id}/maps/{child_map_id}/send",
                json=message_payload,
            )

            assert response.status_code == 200
            assert response.json()["status"] == "processing_started"

            msg1 = websocket.receive_json()
            assert msg1["role"] == "user"
            assert "style layer" in msg1["content"]
            assert msg1["has_tool_calls"] is False

            msg2 = websocket.receive_json()
            assert msg2["ephemeral"] is True
            assert msg2["action"] == "Kue is thinking..."
            assert msg2["status"] == "active"
            assert msg2["updates"]["style_json"] is False

            msg3 = websocket.receive_json()
            assert msg3["ephemeral"] is True
            assert msg3["action"] == "Kue is thinking..."
            assert msg3["status"] == "completed"
            assert msg3["updates"]["style_json"] is False

            msg4 = websocket.receive_json()
            assert msg4["role"] == "assistant"
            assert "apply a custom style" in msg4["content"]
            assert msg4["has_tool_calls"] is True
            assert len(msg4["tool_calls"]) == 1
            assert msg4["tool_calls"][0]["tagline"] == "Setting layer style..."
            assert msg4["tool_calls"][0]["icon"] == "brush"

            msg5 = websocket.receive_json()
            assert msg5["ephemeral"] is True
            assert "Styling layer" in msg5["action"]
            assert msg5["status"] == "active"
            assert msg5["updates"]["style_json"] is True

            msg6 = websocket.receive_json()
            assert msg6["ephemeral"] is True
            assert "Styling layer" in msg6["action"]
            assert msg6["status"] == "completed"
            assert msg6["updates"]["style_json"] is True

            # Tool response message after styling completes
            msg6_tool = websocket.receive_json()
            assert msg6_tool["role"] == "tool"
            assert msg6_tool["tool_response"]["status"] == "success"

            msg7 = websocket.receive_json()
            assert msg7["ephemeral"] is True
            assert msg7["action"] == "Kue is thinking..."
            assert msg7["status"] == "active"
            assert msg7["updates"]["style_json"] is False

            msg8 = websocket.receive_json()
            assert msg8["ephemeral"] is True
            assert msg8["action"] == "Kue is thinking..."
            assert msg8["status"] == "completed"
            assert msg8["updates"]["style_json"] is False

            msg9 = websocket.receive_json()
            assert msg9["role"] == "assistant"
            assert "applied a custom style" in msg9["content"]
            assert msg9["has_tool_calls"] is False

    style_response = sync_auth_client.get(f"/api/maps/{child_map_id}/style.json")
    assert style_response.status_code == 200

    style_json = style_response.json()

    matching_layers = []
    fill_layers = []
    line_layers = []

    for layer in style_json.get("layers", []):
        if layer.get("source") == layer_id:
            matching_layers.append(layer)

            if layer.get("type") == "fill":
                fill_layers.append(layer)
                actual_color = layer.get("paint", {}).get("fill-color")

                assert actual_color == test_fill_color, (
                    f"Expected {test_fill_color}, got {actual_color}"
                )
                assert layer.get("metadata", {}).get("foo") == "bar"

            elif layer.get("type") == "line":
                line_layers.append(layer)

    assert len(fill_layers) == 1, (
        f"Expected at least 1 fill layer with source {layer_id}, found {len(fill_layers)}"
    )
    assert len(line_layers) == 0, (
        f"Expected 0 line layer with source {layer_id}, found {len(line_layers)}"
    )
