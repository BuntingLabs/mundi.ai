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
async def test_project_deletion(auth_client):
    """Test creating a project, deleting it, and verifying it no longer appears in user projects."""

    # 1. Create a new project
    response = await auth_client.post(
        "/api/maps/create",
        json={
            "title": "Test Project for Deletion",
        },
    )
    response.raise_for_status()
    map_data = response.json()
    project_id = map_data["project_id"]
    # 2. Verify project exists in user projects list
    list_response = await auth_client.get("/api/projects/")
    list_response.raise_for_status()
    projects_data = list_response.json()
    print("foobar", list_response.text)

    project_exists = any(
        project["id"] == project_id for project in projects_data["projects"]
    )
    assert project_exists, (
        f"Created project {project_id} not found in user projects list"
    )

    # 3. Delete the project
    delete_response = await auth_client.delete(f"/api/projects/{project_id}")
    delete_response.raise_for_status()

    # 4. Verify project no longer appears in user projects list
    list_response_after = await auth_client.get("/api/projects/")
    list_response_after.raise_for_status()
    projects_data_after = list_response_after.json()
    print("foobar", list_response_after.text)

    project_exists_after = any(
        project["id"] == project_id for project in projects_data_after["projects"]
    )
    assert not project_exists_after, (
        f"Deleted project {project_id} still appears in user projects list"
    )

    # 5. Verify project appears when include_deleted=true
    list_response_with_deleted = await auth_client.get(
        "/api/projects/?include_deleted=true"
    )
    list_response_with_deleted.raise_for_status()
    projects_data_with_deleted = list_response_with_deleted.json()

    deleted_project = next(
        (
            project
            for project in projects_data_with_deleted["projects"]
            if project["id"] == project_id
        ),
        None,
    )
    assert deleted_project is not None, (
        f"Deleted project {project_id} not found when include_deleted=true"
    )
    assert deleted_project["soft_deleted_at"] is not None, (
        f"Deleted project {project_id} should have soft_deleted_at set"
    )


@pytest.mark.anyio
async def test_project_title_update(auth_client):
    response = await auth_client.post(
        "/api/maps/create",
        json={
            "title": "New Map",
        },
    )
    response.raise_for_status()
    map_data = response.json()
    project_id = map_data["project_id"]

    get_response = await auth_client.get(f"/api/projects/{project_id}")
    get_response.raise_for_status()
    project_data = get_response.json()
    assert project_data["title"] == "New Map"

    update_payload = {"title": "Updated Project Title"}
    update_response = await auth_client.post(
        f"/api/projects/{project_id}", json=update_payload
    )
    update_response.raise_for_status()
    update_data = update_response.json()

    assert update_data["updated"] is True

    get_response = await auth_client.get(f"/api/projects/{project_id}")
    get_response.raise_for_status()
    project_data = get_response.json()

    assert project_data["title"] == "Updated Project Title"

    list_response = await auth_client.get("/api/projects/")
    list_response.raise_for_status()
    projects_data = list_response.json()

    project = next(
        (p for p in projects_data["projects"] if p["id"] == project_id),
        None,
    )
    assert project is not None
    assert project["title"] == "Updated Project Title"
