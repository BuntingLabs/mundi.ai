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

from fastapi import Path, Depends, HTTPException

from src.database.models import MundiMap, MundiProject, MapLayer
from src.structures import async_conn
from src.dependencies.session import (
    UserContext,
    verify_session_required,
)
from src.dag import generate_id, ForkReason


async def forked_map(
    original_map_id: str,
    session: UserContext,
    fork_reason: ForkReason,
) -> MundiMap:
    """Fork a map for edit operations and return the new map"""
    user_id = session.get_user_id()

    async with async_conn("forked_map") as conn:
        source_map = await conn.fetchrow(
            """
            SELECT m.id, m.project_id, m.title, m.description, m.layers
            FROM user_mundiai_maps m
            WHERE m.id = $1 AND m.soft_deleted_at IS NULL AND m.owner_uuid = $2
            """,
            original_map_id,
            user_id,
        )
        if not source_map:
            raise HTTPException(404, f"Map {original_map_id} not found")

        new_map_id = generate_id(prefix="M")

        # Determine the fork message based on the reason
        fork_message = (
            "Forked by AI agent"
            if fork_reason == ForkReason.AI_EDIT
            else "Forked by user"
        )

        row = await conn.fetchrow(
            """
            INSERT INTO user_mundiai_maps
            (id, project_id, owner_uuid, parent_map_id, title, description, layers, display_as_diff, fork_reason)
            VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE, $8)
            RETURNING *
            """,
            new_map_id,
            source_map["project_id"],
            user_id,
            original_map_id,
            source_map["title"],
            source_map["description"],
            source_map["layers"] or [],
            fork_reason.value,
        )
        new_map = MundiMap(**dict(row))

        # Copy over all map_layer_styles to the new map
        await conn.execute(
            """
            INSERT INTO map_layer_styles (map_id, layer_id, style_id)
            SELECT $1, layer_id, style_id
            FROM map_layer_styles
            WHERE map_id = $2
            """,
            new_map_id,
            original_map_id,
        )

        # Update project to include the new map
        await conn.execute(
            """
            UPDATE user_mundiai_projects
            SET maps = array_append(maps, $1),
                map_diff_messages = array_append(map_diff_messages, $2)
            WHERE id = $3
            """,
            new_map_id,
            fork_message,
            source_map["project_id"],
        )

    return new_map


async def forked_map_by_ai(
    original_map_id: str = Path(...),
    session: UserContext = Depends(verify_session_required),
) -> MundiMap:
    return await forked_map(original_map_id, session, ForkReason.AI_EDIT)


async def forked_map_by_user(
    original_map_id: str = Path(...),
    session: UserContext = Depends(verify_session_required),
) -> MundiMap:
    return await forked_map(original_map_id, session, ForkReason.USER_EDIT)


async def get_map(
    map_id: str = Path(...),
    session: UserContext = Depends(verify_session_required),
) -> MundiMap:
    """Get a map that the user owns"""
    user_id = session.get_user_id()

    async with async_conn("get_map") as conn:
        map_row = await conn.fetchrow(
            """
            SELECT *
            FROM user_mundiai_maps
            WHERE id = $1 AND owner_uuid = $2 AND soft_deleted_at IS NULL
            """,
            map_id,
            user_id,
        )
        if not map_row:
            raise HTTPException(404, f"Map {map_id} not found")

        return MundiMap(**dict(map_row))


async def get_layer(
    layer_id: str = Path(...),
) -> MapLayer:
    async with async_conn("get_layer") as conn:
        layer_row = await conn.fetchrow(
            """
            SELECT *
            FROM map_layers
            WHERE layer_id = $1
            """,
            layer_id,
        )
        if not layer_row:
            raise HTTPException(404, f"Layer {layer_id} not found")

        return MapLayer(**dict(layer_row))


async def get_project(
    project_id: str = Path(...),
    session: UserContext = Depends(verify_session_required),
) -> MundiProject:
    """Get a project that the user owns"""
    user_id = session.get_user_id()

    async with async_conn("get_project") as conn:
        project_row = await conn.fetchrow(
            """
            SELECT *
            FROM user_mundiai_projects
            WHERE id = $1 AND owner_uuid = $2 AND soft_deleted_at IS NULL
            """,
            project_id,
            user_id,
        )
        if not project_row:
            raise HTTPException(404, f"Project {project_id} not found")

        return MundiProject(**dict(project_row))
