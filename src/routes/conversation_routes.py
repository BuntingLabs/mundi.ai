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

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import uuid
import json
from src.dependencies.session import UserContext, verify_session_required
from src.dependencies.conversation import get_conversation
from src.database.models import Conversation, MundiChatCompletionMessage
from src.structures import (
    async_conn,
    SanitizedMessage,
    convert_mundi_message_to_sanitized,
)

router = APIRouter()


class ConversationCreateRequest(BaseModel):
    project_id: str


class ConversationResponse(BaseModel):
    id: int
    project_id: str
    owner_uuid: uuid.UUID
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    message_count: int
    first_message_map_id: Optional[str] = None


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    request: ConversationCreateRequest,
    session: UserContext = Depends(verify_session_required),
):
    user_id = session.get_user_id()
    async with async_conn("create_conversation") as conn:
        project_row = await conn.fetchrow(
            """
            SELECT id
            FROM user_mundiai_projects
            WHERE id = $1 AND owner_uuid = $2 AND soft_deleted_at IS NULL
            """,
            request.project_id,
            user_id,
        )
        if not project_row:
            raise HTTPException(404, f"Project {request.project_id} not found")

        conversation = await conn.fetchrow(
            """
            INSERT INTO conversations (project_id, owner_uuid, title)
            VALUES ($1, $2, $3)
            RETURNING id, project_id, owner_uuid, title, created_at, updated_at, soft_deleted_at
            """,
            request.project_id,
            user_id,
            "title pending",
        )
        if conversation is None:
            raise HTTPException(500, "Failed to create conversation")

        return ConversationResponse(
            id=conversation["id"],
            project_id=conversation["project_id"],
            owner_uuid=conversation["owner_uuid"],
            title=conversation["title"],
            created_at=conversation["created_at"],
            updated_at=conversation["updated_at"],
            message_count=0,
            first_message_map_id=None,
        )


@router.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    project_id: str,
    session: UserContext = Depends(verify_session_required),
):
    """List all conversations for the current user in a specific project"""
    user_id = session.get_user_id()

    async with async_conn("list_conversations") as conn:
        rows = await conn.fetch(
            """
            SELECT c.id, c.project_id, c.owner_uuid, c.title, c.created_at, c.updated_at,
                   COUNT(ccm.id) as message_count,
                   (SELECT ccm_first.map_id
                    FROM chat_completion_messages ccm_first
                    WHERE ccm_first.conversation_id = c.id
                    ORDER BY ccm_first.created_at ASC
                    LIMIT 1) as first_message_map_id
            FROM conversations c
            LEFT JOIN chat_completion_messages ccm ON c.id = ccm.conversation_id
            WHERE c.owner_uuid = $1 AND c.project_id = $2 AND c.soft_deleted_at IS NULL
            GROUP BY c.id, c.project_id, c.owner_uuid, c.title, c.created_at, c.updated_at
            ORDER BY c.updated_at DESC
            """,
            user_id,
            project_id,
        )

        return [
            ConversationResponse(
                id=row["id"],
                project_id=row["project_id"],
                owner_uuid=row["owner_uuid"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                message_count=row["message_count"],
                first_message_map_id=row["first_message_map_id"],
            )
            for row in rows
        ]


@router.get(
    "/conversations/{conversation_id}/messages", response_model=List[SanitizedMessage]
)
async def get_conversation_messages(
    conversation: Conversation = Depends(get_conversation),
):
    """Get all messages in a conversation"""
    async with async_conn("get_conversation_messages") as conn:
        rows = await conn.fetch(
            """
            SELECT id, conversation_id, map_id, sender_id, message_json, created_at
            FROM chat_completion_messages
            WHERE conversation_id = $1
            ORDER BY created_at ASC
            """,
            conversation.id,
        )

        messages = []
        for row in rows:
            msg_dict = dict(row)
            # Parse message_json when using raw asyncpg
            msg_dict["message_json"] = json.loads(msg_dict["message_json"])
            cc_message = MundiChatCompletionMessage(**msg_dict)
            if cc_message.message_json["role"] == "system":
                continue
            sanitized_payload = convert_mundi_message_to_sanitized(cc_message)
            messages.append(sanitized_payload)
        return messages
