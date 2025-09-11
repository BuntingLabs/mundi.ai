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

import asyncio
import json
import logging
import os
import time
import traceback
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import asyncpg
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from anyio import EndOfStream
from pydantic import BaseModel, ConfigDict

from src.dependencies.session import UserContext, verify_websocket
from src.database.models import Conversation, MundiChatCompletionMessage
from src.structures import (
    get_async_db_connection,
    convert_mundi_message_to_sanitized,
)

logger = logging.getLogger(__name__)


class ConversationRelatedPayload(BaseModel):
    conversation_id: int


class ChatCompletionReferenceNotificationPayload(ConversationRelatedPayload):
    id: int
    map_id: str


class EphemeralNotificationPayload(ConversationRelatedPayload):
    ephemeral: bool
    action_id: str
    layer_id: str | None
    action: str
    timestamp: datetime
    completed_at: datetime | None
    status: str
    bounds: list[float] | None
    updates: dict[str, Any]

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat() if v else None}
    )


class EphemeralErrorNotificationPayload(ConversationRelatedPayload):
    ephemeral: bool
    action_id: str
    error_message: str
    timestamp: datetime
    status: str

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat() if v else None}
    )


# Create router
router = APIRouter()

# Subscriber registry for WebSocket notifications by conversation_id
# (user_id, conversation_id) -> set[asyncio.Queue[str]]
# each queue can handle: EphemeralErrorNotificationPayload | EphemeralNotificationPayload
subscribers_by_conversation = defaultdict(set)
subscribers_lock = asyncio.Lock()

# Track recently disconnected users and their missed messages per conversation
# (user_id, conversation_id) -> {"disconnect_time": float, "missed_messages": deque[(timestamp, payload)]}
recently_disconnected_users: Dict[Tuple[str, int], Dict[str, Any]] = {}
DISCONNECT_TTL = 30.0  # Keep disconnected user data for 30 seconds
MAX_MISSED_MESSAGES = 100  # Limit buffer size per user per conversation

CHAT_CH = "chat_completion_messages_notify"
chat_q: asyncio.Queue[str] = asyncio.Queue()
# Initialize listener task at module level
listener_task = None


def start_chat_listener():
    global listener_task

    if listener_task is None or listener_task.done():
        user = os.environ["POSTGRES_USER"]
        password = os.environ["POSTGRES_PASSWORD"]
        host = os.environ["POSTGRES_HOST"]
        port = os.environ.get("POSTGRES_PORT", "5432")
        db = os.environ["POSTGRES_DB"]
        dsn = f"postgresql://{user}:{password}@{host}:{port}/{db}"
        listener_task = asyncio.create_task(_chat_pg_listener(dsn=dsn))

    return listener_task


@router.on_event("startup")
async def startup_listener():
    start_chat_listener()
    # Start cleanup task for recently disconnected users
    asyncio.create_task(cleanup_recently_disconnected_users())


async def _chat_pg_listener(dsn: str):
    conn = None
    try:
        conn = await asyncpg.connect(dsn)

        await conn.add_listener(
            CHAT_CH,
            lambda _conn, _pid, _channel, payload: asyncio.create_task(
                _broadcast_payload(payload)
            ),
        )

        while True:
            await asyncio.sleep(3600)
    except Exception:
        traceback.print_exc()
    finally:
        try:
            if conn is not None:
                await conn.close()
        except Exception:
            pass


async def cleanup_recently_disconnected_users():
    """Periodically clean up expired disconnected users"""
    while True:
        try:
            await asyncio.sleep(60)  # Run cleanup every minute
            now = time.time()

            # Clean up users who disconnected too long ago
            users_to_remove = []
            for (
                user_id,
                conversation_id,
            ), user_data in recently_disconnected_users.items():
                if now - user_data["disconnect_time"] > DISCONNECT_TTL:
                    users_to_remove.append((user_id, conversation_id))

            # Remove expired users
            for user_key in users_to_remove:
                del recently_disconnected_users[user_key]

        except Exception:
            logger.exception("Error in cleanup_recently_disconnected_users")


async def get_websocket_conversation(
    conversation_id: int, user_context: UserContext
) -> Conversation | None:
    """Get conversation for WebSocket with proper authentication"""
    user_id = user_context.get_user_id()

    async with get_async_db_connection() as conn:
        conversation = await conn.fetchrow(
            """
            SELECT id, project_id, owner_uuid, title, created_at, updated_at, soft_deleted_at
            FROM conversations
            WHERE id = $1 AND owner_uuid = $2 AND soft_deleted_at IS NULL
            """,
            conversation_id,
            user_id,
        )
        if not conversation:
            return None

        return Conversation(
            id=conversation["id"],
            project_id=conversation["project_id"],
            owner_uuid=conversation["owner_uuid"],
            title=conversation["title"],
            created_at=conversation["created_at"],
            updated_at=conversation["updated_at"],
            soft_deleted_at=conversation["soft_deleted_at"],
        )


@router.websocket("/ws/{conversation_id}/messages/updates")
async def ws_conversation_chat(
    ws: WebSocket,
    conversation_id: int,
    user_context: UserContext = Depends(verify_websocket),
):
    # In edit mode, we don't require tokens for WebSocket connections
    auth_mode = os.environ.get("MUNDI_AUTH_MODE")
    token = ws.query_params.get("token")

    if not token and auth_mode != "edit":
        await ws.close(code=4401, reason="No token")
        return

    user_id = user_context.get_user_id()

    # Check if user owns the conversation
    conversation = await get_websocket_conversation(conversation_id, user_context)
    if not conversation:
        await ws.close(code=4403, reason="Unauthorized")
        return

    await ws.accept()
    queue = asyncio.Queue()
    async with subscribers_lock:
        subscribers_by_conversation[conversation_id].add(queue)

    # Check if this user recently disconnected from this specific conversation and replay their missed messages
    user_conversation_key = (user_id, conversation_id)
    if user_conversation_key in recently_disconnected_users:
        user_data = recently_disconnected_users[user_conversation_key]
        missed_messages = user_data["missed_messages"]

        # Replay all missed messages for this specific user on this specific conversation
        for ts, missed_payload in missed_messages:
            queue.put_nowait(missed_payload)

        # Remove user from recently disconnected since they've reconnected to this conversation
        del recently_disconnected_users[user_conversation_key]
    try:
        while True:
            queue_task = asyncio.create_task(queue.get())
            recv_task = asyncio.create_task(ws.receive())

            done, pending = await asyncio.wait(
                {queue_task, recv_task}, return_when=asyncio.FIRST_COMPLETED
            )

            # client closed
            if recv_task in done:
                try:
                    recv_task.result()
                except (WebSocketDisconnect, EndOfStream):
                    pass

                for task in pending:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                break

            # got a payload
            payload = queue_task.result()
            recv_task.cancel()
            with suppress(asyncio.CancelledError):
                await recv_task

            assert (
                isinstance(payload, ChatCompletionReferenceNotificationPayload)
                or isinstance(payload, EphemeralNotificationPayload)
                or isinstance(payload, EphemeralErrorNotificationPayload)
            )

            # Check if this is an ephemeral message
            if isinstance(
                payload,
                (EphemeralNotificationPayload, EphemeralErrorNotificationPayload),
            ):
                # Send ephemeral message directly without DB lookup
                await ws.send_json(payload.model_dump(mode="json"))
                continue
            # Get the full message from the database using the id from notification
            ccref_notification: ChatCompletionReferenceNotificationPayload = payload
            async with get_async_db_connection() as conn:
                message = await conn.fetchrow(
                    """
                    SELECT * FROM chat_completion_messages
                    WHERE id = $1 AND conversation_id = $2
                    """,
                    ccref_notification.id,
                    ccref_notification.conversation_id,
                )

                if message:
                    msg_dict = dict(message)
                    # Parse message_json ... when using raw asyncpg
                    msg_dict["message_json"] = json.loads(msg_dict["message_json"])
                    cc_message = MundiChatCompletionMessage(**msg_dict)
                    if cc_message.message_json["role"] == "system":
                        continue
                    sanitized_payload = convert_mundi_message_to_sanitized(cc_message)
                    await ws.send_json(sanitized_payload.model_dump(mode="json"))

    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Unexpected WebSocket error for conversation {conversation_id}: {e}")
        print(traceback.format_exc())
    finally:
        # Track this user as recently disconnected from this specific conversation
        user_conversation_key = (user_id, conversation_id)
        recently_disconnected_users[user_conversation_key] = {
            "disconnect_time": time.time(),
            "missed_messages": deque(),
        }

        async with subscribers_lock:
            subscribers_by_conversation[conversation_id].discard(queue)
            if not subscribers_by_conversation[conversation_id]:
                del subscribers_by_conversation[conversation_id]


async def _broadcast_payload(payload: str):
    try:
        # Parse the payload to determine its type
        parsed_payload_dict: dict = json.loads(payload)

        parsed_payload: ConversationRelatedPayload | None = None
        if parsed_payload_dict.get("ephemeral"):
            if "error_message" in parsed_payload_dict:
                parsed_payload = EphemeralErrorNotificationPayload(
                    **parsed_payload_dict
                )
            else:
                parsed_payload = EphemeralNotificationPayload(**parsed_payload_dict)
        else:
            # It's a chat completion reference notification
            parsed_payload = ChatCompletionReferenceNotificationPayload(
                **parsed_payload_dict
            )

        # payload only contains like id, conversation_id, and ephemeral
        # if its ephemeral it has other stuff
        assert parsed_payload.conversation_id, "conversation_id is required"

        now = time.time()

        # Store messages for recently disconnected users who might reconnect to this specific conversation
        users_to_remove = []
        for (
            user_id,
            disconnected_conversation_id,
        ), user_data in recently_disconnected_users.items():
            # Clean up users who disconnected too long ago
            if now - user_data["disconnect_time"] > DISCONNECT_TTL:
                users_to_remove.append((user_id, disconnected_conversation_id))
                continue

            # Only store messages for users who were disconnected from this specific conversation
            if disconnected_conversation_id == parsed_payload.conversation_id:
                # Add message to their missed messages buffer
                missed_messages = user_data["missed_messages"]
                missed_messages.append((now, parsed_payload))

                # Limit buffer size
                while len(missed_messages) > MAX_MISSED_MESSAGES:
                    missed_messages.popleft()

        # Remove expired users
        for user_key in users_to_remove:
            del recently_disconnected_users[user_key]

        # Broadcast to live subscribers
        async with subscribers_lock:
            queues = list(
                subscribers_by_conversation.get(parsed_payload.conversation_id, [])
            )
        for q in queues:
            q.put_nowait(parsed_payload)
    except Exception as e:
        raise e
    finally:
        logger.exception("Error broadcasting payload")


@asynccontextmanager
async def kue_ephemeral_action(
    conversation_id: int,
    action_description: str,
    layer_id: str | None = None,
    update_style_json: bool = False,
    bounds: list[float] | None = None,
):
    """
    Async context manager for ephemeral actions.
    Sends a websocket message with the action when entering,
    and automatically removes it when exiting the context.
    """
    payload = EphemeralNotificationPayload(
        conversation_id=conversation_id,
        ephemeral=True,
        action_id=str(uuid.uuid4()),
        layer_id=layer_id,
        action=action_description,
        timestamp=datetime.now(timezone.utc),
        completed_at=None,
        status="active",
        bounds=bounds,
        updates={
            "style_json": update_style_json,
        },
    )

    # Put it on the event loop to prevent race conditions
    await asyncio.sleep(0.05)

    try:
        # Store for recently disconnected users from this specific conversation
        now = time.time()
        users_to_remove = []
        for (
            user_id,
            disconnected_conversation_id,
        ), user_data in recently_disconnected_users.items():
            # Clean up users who disconnected too long ago
            if now - user_data["disconnect_time"] > DISCONNECT_TTL:
                users_to_remove.append((user_id, disconnected_conversation_id))
                continue

            # Only store messages for users who were disconnected from this specific conversation
            if disconnected_conversation_id == conversation_id:
                # Add message to their missed messages buffer
                missed_messages = user_data["missed_messages"]
                missed_messages.append((now, payload))

                # Limit buffer size
                while len(missed_messages) > MAX_MISSED_MESSAGES:
                    missed_messages.popleft()

        # Remove expired users
        for user_key in users_to_remove:
            del recently_disconnected_users[user_key]

        # Broadcast to live subscribers
        async with subscribers_lock:
            queues = list(subscribers_by_conversation.get(conversation_id, []))
        for q in queues:
            q.put_nowait(payload)

        # Yield control back to the caller
        yield payload

    finally:
        # Always send the action completed message
        finished_payload = payload.model_copy()
        finished_payload.status = "completed"
        finished_payload.completed_at = datetime.now(timezone.utc)

        # Store completion for recently disconnected users from this specific conversation
        now = time.time()
        users_to_remove = []
        for (
            user_id,
            disconnected_conversation_id,
        ), user_data in recently_disconnected_users.items():
            # Clean up users who disconnected too long ago
            if now - user_data["disconnect_time"] > DISCONNECT_TTL:
                users_to_remove.append((user_id, disconnected_conversation_id))
                continue

            # Only store messages for users who were disconnected from this specific conversation
            if disconnected_conversation_id == conversation_id:
                # Add message to their missed messages buffer
                missed_messages = user_data["missed_messages"]
                missed_messages.append((now, finished_payload))

                # Limit buffer size
                while len(missed_messages) > MAX_MISSED_MESSAGES:
                    missed_messages.popleft()

        # Remove expired users
        for user_key in users_to_remove:
            del recently_disconnected_users[user_key]

        # Broadcast to live subscribers
        async with subscribers_lock:
            queues = list(subscribers_by_conversation.get(conversation_id, []))
        for q in queues:
            q.put_nowait(finished_payload)


async def kue_notify_error(conversation_id: int, error_message: str):
    """
    Send an ephemeral error notification to the client.
    Unlike kue_ephemeral_action, this is not a context manager and sends a single error message.
    """
    payload = EphemeralErrorNotificationPayload(
        conversation_id=conversation_id,
        ephemeral=True,
        action_id=str(uuid.uuid4()),
        error_message=error_message,
        timestamp=datetime.now(timezone.utc),
        status="error",
    )

    # Store for recently disconnected users from this specific conversation
    now = time.time()
    users_to_remove = []
    for (
        user_id,
        disconnected_conversation_id,
    ), user_data in recently_disconnected_users.items():
        # Clean up users who disconnected too long ago
        if now - user_data["disconnect_time"] > DISCONNECT_TTL:
            users_to_remove.append((user_id, disconnected_conversation_id))
            continue

        # Only store messages for users who were disconnected from this specific conversation
        if disconnected_conversation_id == conversation_id:
            # Add message to their missed messages buffer
            missed_messages = user_data["missed_messages"]
            missed_messages.append((now, payload))

            # Limit buffer size
            while len(missed_messages) > MAX_MISSED_MESSAGES:
                missed_messages.popleft()

    # Remove expired users
    for user_key in users_to_remove:
        del recently_disconnected_users[user_key]

    # Broadcast to live subscribers
    async with subscribers_lock:
        queues = list(subscribers_by_conversation.get(conversation_id, []))
    for q in queues:
        q.put_nowait(payload)
