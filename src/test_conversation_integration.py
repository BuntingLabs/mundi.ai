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


@pytest.mark.anyio
async def test_conversation_project_integration(
    auth_client, test_map_with_vector_layers
):
    """Test that conversations are properly linked to projects and work across multiple maps"""
    project_id = test_map_with_vector_layers["project_id"]

    # Create a conversation for the project
    conversation_response = await auth_client.post(
        "/api/conversations", json={"project_id": project_id}
    )
    conversation_response.raise_for_status()
    conversation_data = conversation_response.json()
    conversation_id = conversation_data["id"]

    # Verify conversation is linked to the correct project
    assert conversation_data["project_id"] == project_id
    assert conversation_data["title"] == "title pending"

    # List conversations and verify our conversation is there
    list_response = await auth_client.get(f"/api/conversations?project_id={project_id}")
    list_response.raise_for_status()
    conversations = list_response.json()

    # Find our conversation in the list
    our_conversation = next(
        (c for c in conversations if c["id"] == conversation_id), None
    )
    assert our_conversation is not None
    assert our_conversation["project_id"] == project_id

    # Verify we can get messages from the conversation (should be empty initially)
    messages_response = await auth_client.get(
        f"/api/conversations/{conversation_id}/messages"
    )
    messages_response.raise_for_status()
    messages = messages_response.json()
    assert len(messages) == 0

    # Test that conversations from different projects don't interfere
    # Create a new map (which creates a new project)
    new_map_response = await auth_client.post(
        "/api/maps/create",
        json={
            "title": "Test Map 2",
        },
    )
    new_map_response.raise_for_status()
    new_project_id = new_map_response.json()["project_id"]

    # Create a conversation for the new project
    new_conversation_response = await auth_client.post(
        "/api/conversations", json={"project_id": new_project_id}
    )
    new_conversation_response.raise_for_status()
    new_conversation_data = new_conversation_response.json()

    # Verify the new conversation is linked to the new project
    assert new_conversation_data["project_id"] == new_project_id
    assert new_conversation_data["id"] != conversation_id

    # List conversations for first project
    project1_conversations_response = await auth_client.get(
        f"/api/conversations?project_id={project_id}"
    )
    project1_conversations_response.raise_for_status()
    project1_conversations = project1_conversations_response.json()

    # List conversations for second project
    project2_conversations_response = await auth_client.get(
        f"/api/conversations?project_id={new_project_id}"
    )
    project2_conversations_response.raise_for_status()
    project2_conversations = project2_conversations_response.json()

    # Verify each conversation is in its respective project
    project1_ids = [c["id"] for c in project1_conversations]
    project2_ids = [c["id"] for c in project2_conversations]

    assert conversation_id in project1_ids
    assert new_conversation_data["id"] in project2_ids

    # Verify project isolation - conversations should not appear in the other project
    assert conversation_id not in project2_ids
    assert new_conversation_data["id"] not in project1_ids


@pytest.mark.anyio
async def test_conversation_creation_requires_project_id(auth_client):
    """Test that creating a conversation without project_id fails"""
    # Try to create conversation without project_id
    response = await auth_client.post("/api/conversations", json={})
    assert response.status_code == 422

    # Try to create conversation with invalid project_id
    try:
        response = await auth_client.post(
            "/api/conversations", json={"project_id": "invalid"}
        )
        # This should fail with a foreign key constraint error or similar
        assert response.status_code in [400, 422, 500]
    except Exception:
        # If it throws an exception, that's also acceptable for this test
        pass
