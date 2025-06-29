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
import os
import time


@pytest.fixture
def sync_test_map_id(sync_auth_client):
    map_title = f"Test WebSocket Map {uuid.uuid4()}"

    map_data = {
        "title": map_title,
        "description": "Map for testing WebSocket functionality",
        "link_accessible": True,
    }

    response = sync_auth_client.post("/api/maps/create", json=map_data)
    assert response.status_code == 200
    map_id = response.json()["id"]

    return map_id


def test_websocket_successful_connection(
    sync_test_map_id, sync_auth_client, websocket_url_for_map
):
    # no errors
    with sync_auth_client.websocket_connect(websocket_url_for_map(sync_test_map_id)):
        pass


def test_websocket_404(sync_auth_client):
    test_map_id = "should-404-doesntexist"

    with pytest.raises(Exception):  # TestClient raises different exceptions
        with sync_auth_client.websocket_connect(
            f"/api/maps/ws/{test_map_id}/messages/updates"
        ):
            pytest.fail("WebSocket connection should have failed without token")


@pytest.mark.skipif(
    os.environ.get("OPENAI_API_KEY") is None or os.environ.get("OPENAI_API_KEY") == "",
    reason="OPENAI_API_KEY is required for this test",
)
def test_websocket_receive_ephemeral_action(
    sync_test_map_id, sync_auth_client, websocket_url_for_map
):
    with sync_auth_client.websocket_connect(
        websocket_url_for_map(sync_test_map_id)
    ) as websocket:
        response = sync_auth_client.post(
            f"/api/maps/{sync_test_map_id}/messages/send",
            json={
                "role": "user",
                "content": "Hello",
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
        assert "map_id" in ephemeral_msg
        assert ephemeral_msg["map_id"] == sync_test_map_id
        assert "ephemeral" in ephemeral_msg
        assert ephemeral_msg["ephemeral"] is True
        assert "action_id" in ephemeral_msg
        assert "action" in ephemeral_msg
        assert "timestamp" in ephemeral_msg
        assert "status" in ephemeral_msg


@pytest.mark.skipif(
    os.environ.get("OPENAI_API_KEY") is None or os.environ.get("OPENAI_API_KEY") == "",
    reason="OPENAI_API_KEY is required for this test",
)
def test_websocket_missed_messages(
    sync_test_map_id, sync_auth_client, websocket_url_for_map
):
    with sync_auth_client.websocket_connect(
        websocket_url_for_map(sync_test_map_id)
    ) as websocket:
        response = sync_auth_client.post(
            f"/api/maps/{sync_test_map_id}/messages/send",
            json={
                "role": "user",
                "content": "Hello",
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
        assert "map_id" in ephemeral_msg
        assert ephemeral_msg["map_id"] == sync_test_map_id
        assert "ephemeral" in ephemeral_msg
        assert ephemeral_msg["ephemeral"] is True
        assert "action_id" in ephemeral_msg
        assert "action" in ephemeral_msg
        assert "timestamp" in ephemeral_msg
        assert "status" in ephemeral_msg

    response2 = sync_auth_client.post(
        f"/api/maps/{sync_test_map_id}/messages/send",
        json={
            "role": "user",
            "content": "Hello again",
        },
    )
    assert response2.status_code == 200

    time.sleep(4)

    with sync_auth_client.websocket_connect(
        websocket_url_for_map(sync_test_map_id)
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
        assert "map_id" in ephemeral_msg
        assert ephemeral_msg["map_id"] == sync_test_map_id
        assert "ephemeral" in ephemeral_msg
        assert ephemeral_msg["ephemeral"] is True
        assert "action_id" in ephemeral_msg
        assert "action" in ephemeral_msg
        assert "timestamp" in ephemeral_msg
        assert "status" in ephemeral_msg
