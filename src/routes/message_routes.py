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

from fastapi import APIRouter, HTTPException, status, Request, Depends
from fastapi.responses import JSONResponse
from typing import List, Union
from pydantic import BaseModel
import logging
import os
import json
import re
from fastapi import BackgroundTasks
from opentelemetry import trace
import pandas as pd
import asyncio
import traceback
from fastapi import UploadFile
import io
import httpx
from typing import Callable
from redis import Redis
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion_tool_message_param import (
    ChatCompletionToolMessageParam,
)
from openai.types.chat.chat_completion_message_param import (
    ChatCompletionUserMessageParam,
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from src.symbology.llm import generate_maplibre_layers_for_layer_id
from src.structures import async_conn
from src.symbology.verify import StyleValidationError, verify_style_json_str
from src.routes.postgres_routes import (
    generate_id,
    get_map_style_internal,
    get_map_description,
    internal_upload_layer,
)
from src.geoprocessing.dispatch import (
    UnsupportedAlgorithmError,
    InvalidInputFormatError,
    get_tools,
)
from src.dependencies.base_map import get_base_map_provider
from src.duckdb import execute_duckdb_query
from src.utils import get_async_s3_client, get_bucket_name
from src.dependencies.postgis import get_postgis_provider
from src.dependencies.layer_describer import LayerDescriber, get_layer_describer
from src.dependencies.chat_completions import ChatArgsProvider, get_chat_args_provider
from src.dependencies.map_state import MapStateProvider, get_map_state_provider
from src.dependencies.system_prompt import (
    SystemPromptProvider,
    get_system_prompt_provider,
)
from src.dependencies.session import (
    verify_session_required,
    UserContext,
)
from src.dependencies.postgres_connection import (
    PostgresConnectionManager,
    get_postgres_connection_manager,
)
from src.utils import get_openai_client
from src.openstreetmap import download_from_openstreetmap, has_openstreetmap_api_key
from src.routes.websocket import kue_ephemeral_action, kue_notify_error

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


redis = Redis(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    decode_responses=True,
)

# Create router
router = APIRouter()


class ChatCompletionMessageRow(BaseModel):
    id: int
    map_id: str
    sender_id: str
    message_json: Union[
        ChatCompletionMessageParam,
        ChatCompletionMessage,
        dict,
    ]
    created_at: str


class MessagesListResponse(BaseModel):
    map_id: str
    messages: List[ChatCompletionMessageRow]


@router.get(
    "/{map_id}/messages",
    # response_model=MessagesListResponse,
    operation_id="get_map_messages",
    response_class=JSONResponse,
)
async def get_map_messages(
    request: Request,
    map_id: str,
    session: UserContext = Depends(verify_session_required),
):
    all_messages = await get_all_map_messages(map_id, session)

    # Filter for messages with role "user" or "assistant" and no tool_calls
    filtered_messages = [
        msg
        for msg in all_messages["messages"]
        if msg.get("message_json", {}).get("role") in ["user", "assistant"]
        and not msg.get("message_json", {}).get("tool_calls")
    ]

    return {
        "map_id": map_id,
        "messages": filtered_messages,
    }


async def get_all_map_messages(
    map_id: str,
    session: UserContext,
):
    async with async_conn("get_all_map_messages") as conn:
        map_result = await conn.fetchrow(
            """
            SELECT id, owner_uuid
            FROM user_mundiai_maps
            WHERE id = $1 AND soft_deleted_at IS NULL
            """,
            map_id,
        )

        if not map_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Map not found"
            )

        if session.get_user_id() != str(map_result["owner_uuid"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        db_messages = await conn.fetch(
            """
            SELECT id, map_id, sender_id, message_json, created_at
            FROM chat_completion_messages
            WHERE map_id = $1
            ORDER BY created_at ASC
            """,
            map_id,
        )

        # We keep everything as dict here, which is because serializing to chat completion row
        # kept fucking up image urls.
        messages = []
        for msg in db_messages:
            msg_dict = dict(msg)
            # Parse message_json if it's a string
            if isinstance(msg_dict["message_json"], str):
                msg_dict["message_json"] = json.loads(msg_dict["message_json"])
            messages.append(msg_dict)

        return {
            "map_id": map_id,
            "messages": messages,
        }


class RecoverableToolCallError(Exception):
    def __init__(self, message: str, tool_call_id: str):
        self.message = message
        self.tool_call_id = tool_call_id
        super().__init__(message)


def is_layer_id(s: str) -> bool:
    return isinstance(s, str) and s[0] == "L" and len(s) == 12


async def run_geoprocessing_tool(
    tool_call: ChatCompletionToolMessageParam,
    conn,
    user_id: str,
    map_id: str,
):
    function_name = tool_call.function.name
    tool_args = json.loads(tool_call.function.arguments)

    all_tools = get_tools()
    for tool in all_tools:
        if function_name == tool["function"]["name"]:
            tool_def = tool
            break
    assert tool_def is not None

    algorithm_id = tool_def["function"]["name"].replace("_", ":")

    mapped_args = tool_args.copy()
    mapped_args["map_id"] = map_id
    mapped_args["user_uuid"] = user_id

    with tracer.start_as_current_span(f"geoprocessing.{algorithm_id}") as span:
        try:
            input_params = {}
            input_urls = {}

            for key, val in mapped_args.items():
                if key == "OUTPUT":
                    continue
                elif is_layer_id(val):
                    # This is a layer ID, get the S3 key from database and create presigned URL
                    layer_data = await conn.fetchrow(
                        """
                        SELECT s3_key FROM map_layers
                        WHERE layer_id = $1 AND owner_uuid = $2
                        """,
                        val,
                        user_id,
                    )

                    if not layer_data or not layer_data["s3_key"]:
                        raise RecoverableToolCallError(
                            f"Layer {val} not found or has no S3 key",
                            tool_call.id,
                        )

                    s3_client = await get_async_s3_client()
                    bucket_name = get_bucket_name()
                    presigned_url = await s3_client.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": bucket_name, "Key": layer_data["s3_key"]},
                        ExpiresIn=3600,
                    )
                    input_urls[key] = presigned_url
                else:
                    input_params[key] = str(val)

            map_data = await conn.fetchrow(
                """
                SELECT project_id FROM user_mundiai_maps
                WHERE id = $1
                """,
                map_id,
            )
            project_id = map_data["project_id"]

            output_layer_mappings = {}

            # Generate presigned PUT URLs for all output parameters
            s3_client = await get_async_s3_client()
            bucket_name = get_bucket_name()
            output_presigned_put_urls = {}

            # Generate output layer ID and S3 key for this output
            output_layer_id = generate_id(prefix="L")
            # Determine file extension based on tool description
            tool_description = tool_def["function"]["description"].lower()
            vector_count = tool_description.count("vector")
            raster_count = tool_description.count("raster")

            if vector_count > raster_count:
                file_extension = ".fgb"
                layer_type = "vector"
            else:
                file_extension = ".tif"
                layer_type = "raster"

            output_s3_key = (
                f"uploads/{user_id}/{project_id}/{output_layer_id}{file_extension}"
            )

            # Generate presigned PUT URL for this output
            output_presigned_url = await s3_client.generate_presigned_url(
                "put_object",
                Params={"Bucket": bucket_name, "Key": output_s3_key},
                ExpiresIn=3600,  # 1 hour
            )

            output_presigned_put_urls["OUTPUT"] = output_presigned_url
            output_layer_mappings["OUTPUT"] = {
                "layer_id": output_layer_id,
                "s3_key": output_s3_key,
                "layer_type": layer_type,
                "file_extension": file_extension,
            }

            qgis_request = {
                "algorithm_id": algorithm_id,
                "qgis_inputs": input_params,
                "output_presigned_put_urls": output_presigned_put_urls,
                "input_urls": input_urls,
            }

            async with kue_ephemeral_action(map_id, f"QGIS running {algorithm_id}..."):
                # Call QGIS processing service
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        os.environ["QGIS_PROCESSING_URL"] + "/run_qgis_process",
                        json=qgis_request,
                        timeout=30.0,
                    )

                if response.status_code != 200:
                    return {
                        "status": "error",
                        "error": f"QGIS processing failed: {response.status_code} - {response.text}",
                        "algorithm_id": algorithm_id,
                    }

                qgis_result = response.json()

                # Check if all layer outputs were successfully uploaded
                upload_results = qgis_result.get("upload_results", {})

                for param_name in output_layer_mappings.keys():
                    if (
                        param_name not in upload_results
                        or not upload_results[param_name]["uploaded"]
                    ):
                        return {
                            "status": "error",
                            "error": f"QGIS processing completed but output file {param_name} was not uploaded successfully",
                            "qgis_result": qgis_result,
                        }

                # Create new layers from the uploaded results
                created_layers = []

                for param_name, layer_info in output_layer_mappings.items():
                    # Download the output file from S3
                    downloaded_file = await s3_client.get_object(
                        Bucket=bucket_name, Key=layer_info["s3_key"]
                    )
                    file_content = await downloaded_file["Body"].read()

                    # Create an UploadFile-like object
                    filename = f"{layer_info['layer_id']}{layer_info['file_extension']}"
                    upload_file = UploadFile(
                        filename=filename,
                        file=io.BytesIO(file_content),
                    )

                    upload_result = await internal_upload_layer(
                        map_id=map_id,
                        file=upload_file,
                        layer_name=filename,
                        add_layer_to_map=True,
                        user_id=user_id,
                        project_id=project_id,
                    )

                    created_layers.append(
                        {
                            "param_name": param_name,
                            "layer_id": upload_result.id,
                            "layer_name": filename,
                            "layer_type": layer_info["layer_type"],
                        }
                    )

                # Prepare the response
                result = {
                    "status": "success",
                    "message": f"{function_name} completed successfully",
                    "algorithm_id": algorithm_id,
                    "qgis_result": qgis_result,
                    "created_layers": created_layers,
                }

                return result

        except UnsupportedAlgorithmError as e:
            return {
                "status": "error",
                "error": f"Unsupported algorithm parameter: {str(e)}",
            }
        except InvalidInputFormatError as e:
            return {
                "status": "error",
                "error": f"Invalid input format: {str(e)}",
            }
        except Exception as e:
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            span.set_attribute("error.traceback", traceback.format_exc())
            return {
                "status": "error",
                "error": f'Unexpected error running geoprocessing: "{str(e)}", this is likely a Mundi bug.',
                "algorithm_id": algorithm_id,
            }


async def process_chat_interaction_task(
    request: Request,  # Keep request for get_map_messages
    map_id: str,
    session: UserContext,  # Pass session for auth
    user_id: str,  # Pass user_id directly
    chat_args: ChatArgsProvider,
    map_state: MapStateProvider,
    system_prompt_provider: SystemPromptProvider,
    connection_manager: PostgresConnectionManager,
):
    # kick it off with a quick sleep, to detach from the event loop blocking /send
    await asyncio.sleep(0.1)

    async with async_conn("process_chat_interaction_task") as conn:

        async def add_chat_completion_message(
            message: Union[ChatCompletionMessage, ChatCompletionMessageParam],
        ):
            message_dict = (
                message.model_dump() if isinstance(message, BaseModel) else message
            )
            await conn.execute(
                """
                INSERT INTO chat_completion_messages
                (map_id, sender_id, message_json)
                VALUES ($1, $2, $3)
                """,
                map_id,
                user_id,
                json.dumps(message_dict),
            )

        with tracer.start_as_current_span("app.process_chat_interaction") as span:
            for i in range(25):
                # Check if the message processing has been cancelled
                if redis.get(f"messages:{map_id}:cancelled"):
                    redis.delete(f"messages:{map_id}:cancelled")
                    break

                # Refresh messages to include any new system messages we just added
                with tracer.start_as_current_span("kue.fetch_messages"):
                    updated_messages_response = await get_all_map_messages(
                        map_id, session
                    )

                openai_messages = [
                    msg["message_json"] for msg in updated_messages_response["messages"]
                ]

                with tracer.start_as_current_span("kue.fetch_unattached_layers"):
                    unattached_layers = await conn.fetch(
                        """
                        SELECT ml.layer_id, ml.created_on, ml.last_edited, ml.type, ml.name
                        FROM map_layers ml
                        WHERE ml.owner_uuid = $1
                        AND NOT EXISTS (
                            SELECT 1 FROM user_mundiai_maps m
                            WHERE ml.layer_id = ANY(m.layers) AND m.owner_uuid = $2
                        )
                        ORDER BY ml.created_on DESC
                        LIMIT 10
                        """,
                        user_id,
                        user_id,
                    )

                layer_enum = {}
                for layer in unattached_layers:
                    layer_name = (
                        layer.get("name") or f"Unnamed Layer ({layer['layer_id'][:8]})"
                    )
                    layer_enum[layer["layer_id"]] = (
                        f"{layer_name} (type: {layer.get('type', 'unknown')}, created: {layer['created_on']})"
                    )

                client = get_openai_client()

                tools_payload = [
                    {
                        "type": "function",
                        "function": {
                            "name": "new_layer_from_postgis",
                            "description": "Creates a new layer, given a PostGIS connection and query, and adds it to the map so the user can see it. Layer will automatically pull data from PostGIS. Modify style using the create_layer_style tool.",
                            "strict": True,
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "postgis_connection_id": {
                                        "type": "string",
                                        "description": "Unique PostGIS connection ID used as source",
                                    },
                                    "query": {
                                        "type": "string",
                                        "description": "SQL query to execute against PostGIS database for this layer, should list fetched columns for attributes that might be used for symbology (+ shape geometry). This query MUST alias the geometry column as 'geom'.",
                                    },
                                    "layer_name": {
                                        "type": "string",
                                        "description": "Sets a human-readable name for this layer. This name will appear in the layer list/legend for the user.",
                                    },
                                },
                                "required": [
                                    "postgis_connection_id",
                                    "query",
                                    "layer_name",
                                ],
                                "additionalProperties": False,
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "add_layer_to_map",
                            "description": "Shows a newly created or existing unattached layer on the user's current map and layer list. Use this after a geoprocessing step that creates a layer, or if the user asks to see an existing layer that isn't currently on their map.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "layer_id": {
                                        "type": "string",
                                        "description": "The ID of the layer to add to the map. Choose from available unattached layers.",
                                        "enum": list(layer_enum.keys())
                                        if layer_enum
                                        else ["NO_UNATTACHED_LAYERS"],
                                    },
                                    "new_name": {
                                        "type": "string",
                                        "description": "Sets a new human-readable name for this layer. This name will appear in the layer list/legend for the user.",
                                    },
                                },
                                "required": ["layer_id", "new_name"],
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "create_layer_style",
                            "description": "Creates a new style for a layer with MapLibre JSON layers. Automatically renders the style for visual inspection.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "layer_id": {
                                        "type": "string",
                                        "description": "The ID of the layer to create a style for",
                                    },
                                    "maplibre_json_layers_str": {
                                        "type": "string",
                                        "description": 'JSON string of MapLibre layer objects. Example: [{"id": "LZJ5RmuZr6qN-line", "type": "line", "source": "LZJ5RmuZr6qN", "paint": {"line-color": "#1E90FF"}}]',
                                    },
                                },
                                "required": ["layer_id", "maplibre_json_layers_str"],
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "set_active_style",
                            "description": "Sets a style as active for a layer in a map",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "layer_id": {
                                        "type": "string",
                                        "description": "The ID of the layer",
                                    },
                                    "style_id": {
                                        "type": "string",
                                        "description": "The ID of the style to set as active",
                                    },
                                },
                                "required": ["layer_id", "style_id"],
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "query_duckdb_sql",
                            "description": "Execute a SQL query against vector layer data using DuckDB",
                            "strict": True,
                            "parameters": {
                                "type": "object",
                                "required": ["layer_ids", "sql_query", "head_n_rows"],
                                "properties": {
                                    "layer_ids": {
                                        "type": "array",
                                        "description": "Load these vector layer IDs as tables",
                                        "items": {"type": "string"},
                                    },
                                    "sql_query": {
                                        "type": "string",
                                        "description": "E.g. SELECT name_en,county FROM LCH6Na2SBvJr ORDER BY id",
                                    },
                                    "head_n_rows": {
                                        "type": "number",
                                        "description": "Truncate result to n rows (increase gingerly, MUST specify returned columns), n=20 is good",
                                    },
                                },
                                "additionalProperties": False,
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "query_postgis_database",
                            "description": "Execute SQL queries on connected PostgreSQL/PostGIS databases. Use for data analysis, spatial queries, and exploring database tables. The query MUST include a LIMIT clause with a value less than 1000.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "postgis_connection_id": {
                                        "type": "string",
                                        "description": "User's PostGIS connection ID to query against",
                                    },
                                    "sql_query": {
                                        "type": "string",
                                        "description": "SQL query to execute. Examples: 'SELECT COUNT(*) FROM table_name', 'SELECT * FROM spatial_table LIMIT 10', 'SELECT column_name FROM information_schema.columns WHERE table_name = \"my_table\"'. Use standard SQL syntax.",
                                    },
                                },
                                "required": ["postgis_connection_id", "sql_query"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "zoom_to_bounds",
                            "description": "Zoom the map to a specific bounding box in WGS84 coordinates. This will save the user's current zoom location to history and navigate to the new bounds.",
                            "strict": True,
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "bounds": {
                                        "type": "array",
                                        "description": "Bounding box in WGS84 format [xmin, ymin, xmax, ymax]",
                                        "items": {"type": "number"},
                                        "minItems": 4,
                                        "maxItems": 4,
                                    },
                                    "zoom_description": {
                                        "type": "string",
                                        "description": 'Complete message to display to the user while zooming, e.g. "Zooming to 39 selected parcels near Ohio"',
                                    },
                                },
                                "required": ["bounds", "zoom_description"],
                                "additionalProperties": False,
                            },
                        },
                    },
                ]

                # Conditionally add OpenStreetMap tool if API key is configured
                if has_openstreetmap_api_key():
                    tools_payload.append(
                        {
                            "type": "function",
                            "function": {
                                "name": "download_from_openstreetmap",
                                "description": "Download features from OSM and add to project as a cloud FlatGeobuf layer",
                                "strict": True,
                                "parameters": {
                                    "type": "object",
                                    "required": [
                                        "tags",
                                        "bbox",
                                        "new_layer_name",
                                    ],
                                    "properties": {
                                        "tags": {
                                            "type": "string",
                                            "description": "Tags to filter for e.g. leisure=park, use & to AND tags together e.g. highway=footway&name=*, no commas",
                                        },
                                        "bbox": {
                                            "type": "array",
                                            "description": "Bounding box in [xmin, ymin, xmax, ymax] format e.g. [9.023802,39.172149,9.280779,39.275211] for Cagliari, Italy",
                                            "items": {"type": "number"},
                                        },
                                        "new_layer_name": {
                                            "type": "string",
                                            "description": "Human-friendly name e.g. Walking paths or Liquor stores in Seattle",
                                        },
                                    },
                                    "additionalProperties": False,
                                },
                            },
                        }
                    )

                all_tools = get_tools()
                tools_payload.extend(all_tools)
                geoprocessing_function_names = [
                    tool["function"]["name"] for tool in all_tools
                ]

                if not layer_enum:
                    add_layer_tool = next(
                        tool
                        for tool in tools_payload
                        if tool["function"]["name"] == "add_layer_to_map"
                    )
                    add_layer_tool["function"]["parameters"]["properties"][
                        "layer_id"
                    ].pop("enum", None)

                # Replace the thinking ephemeral updates with context manager
                async with kue_ephemeral_action(map_id, "Kue is thinking..."):
                    chat_completions_args = await chat_args.get_args(
                        user_id, "send_map_message_async"
                    )
                    with tracer.start_as_current_span(
                        "kue.openai.chat.completions.create"
                    ):
                        # chat.completions.create fails for bad messages and tools, so
                        # if we have orphaned tool calls then we'll get an error - but not
                        # handling it properly makes for a horrible user experience
                        try:
                            response = await client.chat.completions.create(
                                **chat_completions_args,
                                messages=[
                                    {
                                        "role": "system",
                                        "content": system_prompt_provider.get_system_prompt(),
                                    }
                                ]
                                + openai_messages,
                                tools=tools_payload if tools_payload else None,
                                tool_choice="auto" if tools_payload else None,
                            )
                        except Exception as e:
                            await kue_notify_error(
                                map_id,
                                "Error connecting to LLM. If trying again doesn't work, hit the save button in the bottom right of the layer list to reset the chat history.",
                            )
                            span.set_status(
                                trace.Status(trace.StatusCode.ERROR, str(e))
                            )
                            span.set_attribute(
                                "error.traceback", traceback.format_exc()
                            )
                            break

                assistant_message = response.choices[0].message

                # Store the assistant message in the database
                await add_chat_completion_message(assistant_message)

                # If no tool calls, break
                if not assistant_message.tool_calls:
                    break

                for tool_call in assistant_message.tool_calls:
                    function_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    tool_result = {}

                    span.add_event(
                        "kue.tool_call_started",
                        {"tool_name": function_name},
                    )
                    with tracer.start_as_current_span(f"kue.{function_name}") as span:
                        if function_name == "new_layer_from_postgis":
                            postgis_connection_id = tool_args.get(
                                "postgis_connection_id"
                            )
                            query = tool_args.get("query")
                            layer_name = tool_args.get("layer_name")

                            if not postgis_connection_id or not query:
                                tool_result = {
                                    "status": "error",
                                    "error": "Missing required parameters (postgis_connection_id or query).",
                                }
                            else:
                                # Verify the PostGIS connection exists and user has access
                                connection_result = await conn.fetchrow(
                                    """
                                    SELECT connection_uri FROM project_postgres_connections
                                    WHERE id = $1 AND user_id = $2
                                    """,
                                    postgis_connection_id,
                                    user_id,
                                )

                                if not connection_result:
                                    tool_result = {
                                        "status": "error",
                                        "error": f"PostGIS connection '{postgis_connection_id}' not found or you do not have access to it.",
                                    }
                                else:
                                    async with kue_ephemeral_action(
                                        map_id,
                                        "Adding layer from PostGIS...",
                                        update_style_json=True,
                                    ):
                                        try:
                                            # Use connection manager for PostGIS operations
                                            pg = await connection_manager.connect_to_postgres(
                                                postgis_connection_id
                                            )
                                            try:
                                                # 1. Make sure the SQL parsers and planners are happy
                                                await pg.execute(
                                                    f"EXPLAIN {query}"
                                                )  # catches typos & ambiguous refs

                                                # 2. Make sure it returns a geometry column called geom
                                                await pg.execute(
                                                    f"""
                                                    SELECT 1
                                                    FROM   ({query}) AS sub
                                                    WHERE  geom IS NOT NULL
                                                    LIMIT 1
                                                    """
                                                )

                                                # Calculate feature count, bounds, and geometry type for the PostGIS layer
                                                feature_count = None
                                                bounds = None
                                                geometry_type = None

                                                # Calculate feature count
                                                count_result = await pg.fetchval(
                                                    f"SELECT COUNT(*) FROM ({query}) AS sub"
                                                )
                                                feature_count = (
                                                    int(count_result)
                                                    if count_result is not None
                                                    else None
                                                )

                                                # Find geometry column by trying common names
                                                geometry_column = None
                                                common_geom_names = [
                                                    "geom",
                                                    "geometry",
                                                    "shape",
                                                    "the_geom",
                                                    "wkb_geometry",
                                                ]

                                                for geom_name in common_geom_names:
                                                    try:
                                                        await pg.fetchval(
                                                            f"SELECT 1 FROM ({query}) AS sub WHERE {geom_name} IS NOT NULL LIMIT 1"
                                                        )
                                                        geometry_column = geom_name
                                                        break
                                                    except Exception:
                                                        continue

                                                if geometry_column:
                                                    # Detect geometry type for styling
                                                    geometry_type_result = await pg.fetchrow(
                                                        f"""
                                                        SELECT ST_GeometryType({geometry_column}) as geom_type, COUNT(*) as count
                                                        FROM ({query}) AS sub
                                                        WHERE {geometry_column} IS NOT NULL
                                                        GROUP BY ST_GeometryType({geometry_column})
                                                        ORDER BY count DESC
                                                        LIMIT 1
                                                        """
                                                    )

                                                    if (
                                                        geometry_type_result
                                                        and geometry_type_result[
                                                            "geom_type"
                                                        ]
                                                    ):
                                                        # Convert PostGIS geometry type to standard format
                                                        geometry_type = (
                                                            geometry_type_result[
                                                                "geom_type"
                                                            ]
                                                            .replace("ST_", "")
                                                            .lower()
                                                        )

                                                    # Calculate bounds with proper SRID handling
                                                    # ST_Extent returns BOX2D with SRID 0, so we need to set the SRID before transforming
                                                    bounds_result = await pg.fetchrow(
                                                        f"""
                                                        WITH extent_data AS (
                                                            SELECT
                                                                ST_Extent({geometry_column}) as extent_geom,
                                                                (SELECT ST_SRID({geometry_column}) FROM ({query}) AS sub2 WHERE {geometry_column} IS NOT NULL LIMIT 1) as original_srid
                                                            FROM ({query}) AS sub
                                                            WHERE {geometry_column} IS NOT NULL
                                                        )
                                                        SELECT
                                                            CASE
                                                                WHEN original_srid = 4326 THEN
                                                                    ST_XMin(extent_geom)
                                                                ELSE
                                                                    ST_XMin(ST_Transform(ST_SetSRID(extent_geom, original_srid), 4326))
                                                            END as xmin,
                                                            CASE
                                                                WHEN original_srid = 4326 THEN
                                                                    ST_YMin(extent_geom)
                                                                ELSE
                                                                    ST_YMin(ST_Transform(ST_SetSRID(extent_geom, original_srid), 4326))
                                                            END as ymin,
                                                            CASE
                                                                WHEN original_srid = 4326 THEN
                                                                    ST_XMax(extent_geom)
                                                                ELSE
                                                                    ST_XMax(ST_Transform(ST_SetSRID(extent_geom, original_srid), 4326))
                                                            END as xmax,
                                                            CASE
                                                                WHEN original_srid = 4326 THEN
                                                                    ST_YMax(extent_geom)
                                                                ELSE
                                                                    ST_YMax(ST_Transform(ST_SetSRID(extent_geom, original_srid), 4326))
                                                            END as ymax
                                                        FROM extent_data
                                                        WHERE extent_geom IS NOT NULL
                                                        """
                                                    )

                                                    if bounds_result and all(
                                                        v is not None
                                                        for v in bounds_result
                                                    ):
                                                        bounds = [
                                                            float(
                                                                bounds_result["xmin"]
                                                            ),
                                                            float(
                                                                bounds_result["ymin"]
                                                            ),
                                                            float(
                                                                bounds_result["xmax"]
                                                            ),
                                                            float(
                                                                bounds_result["ymax"]
                                                            ),
                                                        ]
                                                else:
                                                    print(
                                                        "Warning: No geometry column found in PostGIS query"
                                                    )
                                            finally:
                                                await pg.close()

                                            # Generate a new layer ID
                                            layer_id = generate_id(prefix="L")

                                            # Generate default style if geometry type was detected
                                            maplibre_layers = None
                                            if geometry_type:
                                                try:
                                                    maplibre_layers = generate_maplibre_layers_for_layer_id(
                                                        layer_id, geometry_type
                                                    )
                                                    # PostGIS layers use MVT tiles, so source-layer is 'reprojectedfgb'
                                                    # This matches the expectation in the style generation function
                                                    print(
                                                        f"Generated default style for PostGIS layer {layer_id} with geometry type {geometry_type}"
                                                    )
                                                except Exception as e:
                                                    print(
                                                        f"Warning: Failed to generate default style for PostGIS layer: {str(e)}"
                                                    )
                                                    maplibre_layers = None

                                            # Create the layer in the database
                                            await conn.execute(
                                                """
                                                INSERT INTO map_layers
                                                (layer_id, owner_uuid, name, path, type, postgis_connection_id, postgis_query, feature_count, bounds, geometry_type, source_map_id, created_on, last_edited)
                                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                                                """,
                                                layer_id,
                                                user_id,
                                                layer_name,
                                                "",  # Empty path for PostGIS layers
                                                "postgis",
                                                postgis_connection_id,
                                                query,
                                                feature_count,
                                                bounds,
                                                geometry_type,
                                                map_id,
                                            )

                                            # Create default style in separate table if we have geometry type
                                            if maplibre_layers:
                                                style_id = generate_id(prefix="S")
                                                await conn.execute(
                                                    """
                                                    INSERT INTO layer_styles
                                                    (style_id, layer_id, style_json, created_by, created_on)
                                                    VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                                                    """,
                                                    style_id,
                                                    layer_id,
                                                    json.dumps(maplibre_layers),
                                                    user_id,
                                                )

                                                await conn.execute(
                                                    """
                                                    INSERT INTO map_layer_styles
                                                    (map_id, layer_id, style_id)
                                                    VALUES ($1, $2, $3)
                                                    """,
                                                    map_id,
                                                    layer_id,
                                                    style_id,
                                                )

                                            # layers may be NULL, not necessarily initialized to []
                                            await conn.execute(
                                                """
                                                UPDATE user_mundiai_maps
                                                SET layers = CASE
                                                    WHEN layers IS NULL THEN ARRAY[$1]
                                                    ELSE array_append(layers, $1)
                                                END
                                                WHERE id = $2 AND (layers IS NULL OR NOT ($1 = ANY(layers)))
                                                """,
                                                layer_id,
                                                map_id,
                                            )

                                            tool_result = {
                                                "status": "success",
                                                "message": f"PostGIS layer created successfully with ID: {layer_id} and added to map",
                                                "layer_id": layer_id,
                                                "query": query,
                                                "added_to_map": True,
                                            }
                                        except Exception as e:
                                            tool_result = {
                                                "status": "error",
                                                "error": f"Query validation failed: {str(e)}",
                                            }

                            await add_chat_completion_message(
                                ChatCompletionToolMessageParam(
                                    role="tool",
                                    tool_call_id=tool_call.id,
                                    content=json.dumps(tool_result),
                                )
                            )
                        elif function_name == "add_layer_to_map":
                            layer_id_to_add = tool_args.get("layer_id")
                            new_name = tool_args.get("new_name")

                            async with kue_ephemeral_action(
                                map_id, "Adding layer to map...", update_style_json=True
                            ):
                                layer_exists = await conn.fetchrow(
                                    """
                                    SELECT layer_id FROM map_layers
                                    WHERE layer_id = $1 AND owner_uuid = $2
                                    """,
                                    layer_id_to_add,
                                    user_id,
                                )

                                if not layer_exists:
                                    tool_result = {
                                        "status": "error",
                                        "error": f"Layer ID '{layer_id_to_add}' not found or you do not have permission to use it.",
                                    }
                                else:
                                    await conn.execute(
                                        """
                                        UPDATE map_layers SET name = $1 WHERE layer_id = $2
                                        """,
                                        new_name,
                                        layer_id_to_add,
                                    )

                                    await conn.execute(
                                        """
                                        UPDATE user_mundiai_maps
                                        SET layers = CASE
                                            WHEN layers IS NULL THEN ARRAY[$1]
                                            ELSE array_append(layers, $1)
                                        END
                                        WHERE id = $2 AND (layers IS NULL OR NOT ($1 = ANY(layers)))
                                        """,
                                        layer_id_to_add,
                                        map_id,
                                    )
                                    tool_result = {
                                        "status": f"Layer '{new_name}' (ID: {layer_id_to_add}) added to map '{map_id}'.",
                                        "layer_id": layer_id_to_add,
                                        "name": new_name,
                                    }

                                await add_chat_completion_message(
                                    ChatCompletionToolMessageParam(
                                        role="tool",
                                        tool_call_id=tool_call.id,
                                        content=json.dumps(tool_result),
                                    )
                                )
                        elif function_name == "query_duckdb_sql":
                            layer_id = tool_args.get("layer_ids", [None])[
                                0
                            ]  # Use first layer or None
                            sql_query = tool_args.get("sql_query")
                            head_n_rows = tool_args.get("head_n_rows", 20)

                            layer_exists = await conn.fetchrow(
                                """
                                SELECT layer_id FROM map_layers
                                WHERE layer_id = $1 AND owner_uuid = $2
                                """,
                                layer_id,
                                user_id,
                            )

                            if not layer_exists:
                                tool_result = {
                                    "status": "error",
                                    "error": f"Layer ID '{layer_id}' not found or you do not have permission to access it.",
                                }
                                await add_chat_completion_message(
                                    ChatCompletionToolMessageParam(
                                        role="tool",
                                        tool_call_id=tool_call.id,
                                        content=json.dumps(tool_result),
                                    )
                                )
                                continue

                            try:
                                # Execute the query using the async function
                                async with kue_ephemeral_action(
                                    map_id, "Querying with SQL...", layer_id=layer_id
                                ):
                                    result = await execute_duckdb_query(
                                        sql_query=sql_query,
                                        layer_id=layer_id,
                                        max_n_rows=head_n_rows,
                                        timeout=10,
                                    )

                                # Convert result to CSV format
                                df = pd.DataFrame(
                                    result["result"], columns=result["headers"]
                                )
                                result_text = df.to_csv(index=False)

                                if len(result_text) > 25000:
                                    tool_result = {
                                        "status": "error",
                                        "error": f"DuckDB CSV result too large: {len(result_text)} characters exceeds 25,000 character limit, try reducing columns or head_n_rows",
                                    }
                                else:
                                    tool_result = {
                                        "status": "success",
                                        "result": result_text,
                                        "row_count": result["row_count"],
                                        "query": sql_query,
                                    }
                            except HTTPException as e:
                                tool_result = {
                                    "status": "error",
                                    "error": f"DuckDB query error: {e.detail}",
                                }
                            except Exception as e:
                                tool_result = {
                                    "status": "error",
                                    "error": f"Error executing SQL query: {str(e)}",
                                }

                            await add_chat_completion_message(
                                ChatCompletionToolMessageParam(
                                    role="tool",
                                    tool_call_id=tool_call.id,
                                    content=json.dumps(tool_result),
                                )
                            )
                        elif function_name == "create_layer_style":
                            layer_id = tool_args.get("layer_id")
                            maplibre_json_layers_str = tool_args.get(
                                "maplibre_json_layers_str"
                            )

                            if not layer_id or not maplibre_json_layers_str:
                                tool_result = {
                                    "status": "error",
                                    "error": "Missing required parameters (layer_id or maplibre_json_layers_str).",
                                }
                            else:
                                # Generate a new style ID
                                style_id = generate_id(prefix="S")

                                try:
                                    layers = json.loads(maplibre_json_layers_str)

                                    # Validate that layers is a list
                                    if not isinstance(layers, list):
                                        raise ValueError(
                                            f"Expected a JSON array of layer objects, but got {type(layers).__name__}: {repr(layers)[:200]}"
                                        )

                                    # Add source-layer property if missing to fix KeyError: 'source-layer'
                                    for layer in layers:
                                        if isinstance(layer, dict):
                                            layer["source-layer"] = "reprojectedfgb"
                                        else:
                                            raise ValueError(
                                                f"Expected layer object to be a dict, but got {type(layer).__name__}: {repr(layer)[:200]}"
                                            )

                                    # Get complete map style with our layer styling to validate it
                                    base_map_provider = get_base_map_provider()
                                    style_json = await get_map_style_internal(
                                        map_id=map_id,
                                        base_map=base_map_provider,
                                        only_show_inline_sources=True,
                                        override_layers=json.dumps({layer_id: layers}),
                                    )

                                    # Validate the complete style
                                    verify_style_json_str(json.dumps(style_json))

                                    # If validation passes, create the style in the database
                                    await conn.execute(
                                        """
                                        INSERT INTO layer_styles
                                        (style_id, layer_id, style_json, created_by)
                                        VALUES ($1, $2, $3, $4)
                                        """,
                                        style_id,
                                        layer_id,
                                        json.dumps(layers),
                                        user_id,
                                    )

                                    tool_result = {
                                        "status": "success",
                                        "style_id": style_id,
                                        "layer_id": layer_id,
                                    }
                                except json.JSONDecodeError as e:
                                    print(f"JSON decode error: {str(e)}")
                                    tool_result = {
                                        "status": "error",
                                        "error": f"Invalid JSON format: {str(e)}",
                                        "layer_id": layer_id,
                                    }
                                except ValueError as e:
                                    print(f"Value error in layer style: {str(e)}")
                                    tool_result = {
                                        "status": "error",
                                        "error": str(e),
                                        "layer_id": layer_id,
                                    }
                                except StyleValidationError as e:
                                    print(
                                        f"Style validation error: {str(e)}",
                                        traceback.format_exc(),
                                        type(e),
                                    )
                                    tool_result = {
                                        "status": "error",
                                        "error": f"Style validation failed: {str(e)}",
                                        "layer_id": layer_id,
                                    }

                            await add_chat_completion_message(
                                ChatCompletionToolMessageParam(
                                    role="tool",
                                    tool_call_id=tool_call.id,
                                    content=json.dumps(tool_result),
                                ),
                            )
                        elif function_name == "set_active_style":
                            layer_id = tool_args.get("layer_id")
                            style_id = tool_args.get("style_id")

                            if not all([layer_id, style_id]):
                                tool_result = {
                                    "status": "error",
                                    "error": "Missing required parameters (layer_id, or style_id).",
                                }
                            else:
                                # Add or update the map_layer_styles entry
                                async with kue_ephemeral_action(
                                    map_id,
                                    "Choosing a new style",
                                    update_style_json=True,
                                ):
                                    await conn.execute(
                                        """
                                        INSERT INTO map_layer_styles (map_id, layer_id, style_id)
                                        VALUES ($1, $2, $3)
                                        ON CONFLICT (map_id, layer_id)
                                        DO UPDATE SET style_id = $3
                                        """,
                                        map_id,
                                        layer_id,
                                        style_id,
                                    )

                                tool_result = {
                                    "status": "success",
                                    "message": f"Style {style_id} set as active for layer {layer_id}, user can now see it",
                                    "layer_id": layer_id,
                                    "style_id": style_id,
                                }

                            await add_chat_completion_message(
                                ChatCompletionToolMessageParam(
                                    role="tool",
                                    tool_call_id=tool_call.id,
                                    content=json.dumps(tool_result),
                                ),
                            )
                        elif function_name == "download_from_openstreetmap":
                            tags = tool_args.get("tags")
                            bbox = tool_args.get("bbox")
                            new_layer_name = tool_args.get("new_layer_name")

                            if not all([tags, bbox, new_layer_name]):
                                tool_result = {
                                    "status": "error",
                                    "error": "Missing required parameters for OpenStreetMap download.",
                                }
                            else:
                                try:
                                    # Keep context manager only around the specific API call
                                    async with kue_ephemeral_action(
                                        map_id,
                                        f"Downloading data from OpenStreetMap: {tags}",
                                    ):
                                        tool_result = await download_from_openstreetmap(
                                            request=request,
                                            map_id=map_id,
                                            bbox=bbox,
                                            tags=tags,
                                            new_layer_name=new_layer_name,
                                            session=session,
                                        )
                                except Exception as e:
                                    print(traceback.format_exc())
                                    print(e)
                                    tool_result = {
                                        "status": "error",
                                        "error": f"Error downloading from OpenStreetMap: {str(e)}",
                                    }
                            # Add instructions to tool result if download was successful
                            if tool_result.get(
                                "status"
                            ) == "success" and tool_result.get("uploaded_layers"):
                                uploaded_layers = tool_result.get("uploaded_layers")
                                layer_names = [
                                    f"{new_layer_name}_{layer['geometry_type']}"
                                    for layer in uploaded_layers
                                ]
                                layer_ids = [
                                    layer["layer_id"] for layer in uploaded_layers
                                ]
                                tool_result["kue_instructions"] = (
                                    f"New layers available: {', '.join(layer_names)} "
                                    f"(IDs: {', '.join(layer_ids)}), all currently invisible. "
                                    'To make any of these visible to the user on their map, use "add_layer_to_map" with the layer_id and a descriptive new_name.'
                                )

                            await add_chat_completion_message(
                                ChatCompletionToolMessageParam(
                                    role="tool",
                                    tool_call_id=tool_call.id,
                                    content=json.dumps(tool_result),
                                ),
                            )
                        elif function_name == "query_postgis_database":
                            postgis_connection_id = tool_args.get(
                                "postgis_connection_id"
                            )
                            sql_query = tool_args.get("sql_query")

                            if not postgis_connection_id or not sql_query:
                                tool_result = {
                                    "status": "error",
                                    "error": "Missing required parameters (postgis_connection_id or sql_query)",
                                }
                            else:
                                # Verify the PostGIS connection exists and user has access
                                connection_result = await conn.fetchrow(
                                    """
                                    SELECT connection_uri FROM project_postgres_connections
                                    WHERE id = $1 AND user_id = $2
                                    """,
                                    postgis_connection_id,
                                    user_id,
                                )

                                if not connection_result:
                                    tool_result = {
                                        "status": "error",
                                        "error": f"PostGIS connection '{postgis_connection_id}' not found or you do not have access to it.",
                                    }
                                else:
                                    try:
                                        # Check if LIMIT is already present and validate it
                                        limited_query = sql_query.strip()
                                        limit_match = re.search(
                                            r"\bLIMIT\s+(\d+)\b",
                                            limited_query,
                                            re.IGNORECASE,
                                        )

                                        if limit_match:
                                            limit_value = int(limit_match.group(1))
                                            if limit_value > 1000:
                                                tool_result = {
                                                    "status": "error",
                                                    "error": f"LIMIT value {limit_value} exceeds maximum allowed limit of 1000",
                                                }
                                                await add_chat_completion_message(
                                                    ChatCompletionToolMessageParam(
                                                        role="tool",
                                                        tool_call_id=tool_call.id,
                                                        content=json.dumps(tool_result),
                                                    ),
                                                )
                                                continue
                                        else:
                                            # No LIMIT found, require explicit LIMIT
                                            tool_result = {
                                                "status": "error",
                                                "error": "Query must include a LIMIT clause with a value less than 1000",
                                            }
                                            await add_chat_completion_message(
                                                ChatCompletionToolMessageParam(
                                                    role="tool",
                                                    tool_call_id=tool_call.id,
                                                    content=json.dumps(tool_result),
                                                ),
                                            )
                                            continue

                                        async with kue_ephemeral_action(
                                            map_id, "Querying PostgreSQL database..."
                                        ):
                                            postgres_conn = await connection_manager.connect_to_postgres(
                                                postgis_connection_id
                                            )
                                            try:
                                                # Execute the query
                                                rows = await postgres_conn.fetch(
                                                    limited_query
                                                )

                                                if not rows:
                                                    tool_result = {
                                                        "status": "success",
                                                        "message": "Query executed successfully but returned no rows",
                                                        "row_count": 0,
                                                        "query": limited_query,
                                                    }
                                                else:
                                                    # Convert rows to list of dicts
                                                    result_data = [
                                                        dict(row) for row in rows
                                                    ]

                                                    # Format the result as a readable string
                                                    if (
                                                        len(result_data) == 1
                                                        and len(result_data[0]) == 1
                                                    ):
                                                        # Single value result
                                                        single_value = list(
                                                            result_data[0].values()
                                                        )[0]
                                                        result_text = f"Query result: {single_value}"
                                                    else:
                                                        # Table format
                                                        if result_data:
                                                            headers = list(
                                                                result_data[0].keys()
                                                            )
                                                            result_lines = [
                                                                "\t".join(headers)
                                                            ]
                                                            for row in result_data:
                                                                result_lines.append(
                                                                    "\t".join(
                                                                        str(
                                                                            row.get(
                                                                                h, ""
                                                                            )
                                                                        )
                                                                        for h in headers
                                                                    )
                                                                )
                                                            result_text = "\n".join(
                                                                result_lines
                                                            )
                                                        else:
                                                            result_text = "No results"

                                                    # Check if result is too large
                                                    if len(result_text) > 25000:
                                                        tool_result = {
                                                            "status": "error",
                                                            "error": f"Query result too large: {len(result_text)} characters exceeds 25,000 character limit. Try reducing the number of columns or rows.",
                                                        }
                                                    else:
                                                        tool_result = {
                                                            "status": "success",
                                                            "result": result_text,
                                                            "row_count": len(
                                                                result_data
                                                            ),
                                                            "query": limited_query,
                                                        }
                                            finally:
                                                await postgres_conn.close()

                                    except Exception as e:
                                        tool_result = {
                                            "status": "error",
                                            "error": f"PostgreSQL query error: {str(e)}",
                                            "query": limited_query,
                                        }

                            await add_chat_completion_message(
                                ChatCompletionToolMessageParam(
                                    role="tool",
                                    tool_call_id=tool_call.id,
                                    content=json.dumps(tool_result),
                                ),
                            )
                        elif function_name == "zoom_to_bounds":
                            bounds = tool_args.get("bounds")
                            description = tool_args.get("zoom_description", "")

                            if not bounds or len(bounds) != 4:
                                tool_result = {
                                    "status": "error",
                                    "error": "Invalid bounds. Must be an array of 4 numbers [west, south, east, north]",
                                }
                            else:
                                try:
                                    # Validate bounds format
                                    west, south, east, north = bounds
                                    if not all(
                                        isinstance(coord, (int, float))
                                        for coord in bounds
                                    ):
                                        raise ValueError(
                                            "All bounds coordinates must be numbers"
                                        )

                                    if west >= east or south >= north:
                                        raise ValueError(
                                            "Invalid bounds: west must be < east and south must be < north"
                                        )

                                    if not (
                                        -180 <= west <= 180
                                        and -180 <= east <= 180
                                        and -90 <= south <= 90
                                        and -90 <= north <= 90
                                    ):
                                        raise ValueError(
                                            "Bounds must be in valid WGS84 range"
                                        )

                                    # Send ephemeral action to trigger zoom on frontend
                                    async with kue_ephemeral_action(
                                        map_id,
                                        description,
                                        update_style_json=False,
                                        bounds=bounds,
                                    ):
                                        await asyncio.sleep(0.5)

                                    tool_result = {
                                        "status": "success",
                                        "bounds": bounds,
                                    }
                                except ValueError as e:
                                    tool_result = {
                                        "status": "error",
                                        "error": str(e),
                                    }
                                except Exception as e:
                                    tool_result = {
                                        "status": "error",
                                        "error": f"Error zooming to bounds: {str(e)}",
                                    }

                            await add_chat_completion_message(
                                ChatCompletionToolMessageParam(
                                    role="tool",
                                    tool_call_id=tool_call.id,
                                    content=json.dumps(tool_result),
                                ),
                            )
                        elif function_name in geoprocessing_function_names:
                            tool_result = await run_geoprocessing_tool(
                                tool_call,
                                conn,
                                user_id,
                                map_id,
                            )
                            await add_chat_completion_message(
                                ChatCompletionToolMessageParam(
                                    role="tool",
                                    tool_call_id=tool_call.id,
                                    content=json.dumps(tool_result),
                                ),
                            )
                        else:
                            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

            # Async connections auto-commit, no need for explicit commit

        # Unlock the map when processing is complete
        redis.delete(f"map_lock:{map_id}")


class MessageSendResponse(BaseModel):
    message_id: str
    status: str


@router.post(
    "/{map_id}/messages/send",
    response_model=MessageSendResponse,
    operation_id="send_map_message",
)
async def send_map_message(
    request: Request,
    map_id: str,
    message: ChatCompletionUserMessageParam,
    background_tasks: BackgroundTasks,
    session: UserContext = Depends(verify_session_required),
    postgis_provider: Callable = Depends(get_postgis_provider),
    layer_describer: LayerDescriber = Depends(get_layer_describer),
    chat_args: ChatArgsProvider = Depends(get_chat_args_provider),
    map_state: MapStateProvider = Depends(get_map_state_provider),
    system_prompt_provider: SystemPromptProvider = Depends(get_system_prompt_provider),
    connection_manager: PostgresConnectionManager = Depends(
        get_postgres_connection_manager
    ),
):
    async with async_conn("send_map_message.authenticate") as conn:
        # Authenticate and check map
        map_result = await conn.fetchrow(
            "SELECT owner_uuid FROM user_mundiai_maps WHERE id = $1 AND soft_deleted_at IS NULL",
            map_id,
        )

    if not map_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Map not found"
        )

    user_id = session.get_user_id()
    if user_id != str(map_result["owner_uuid"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    # Check if map is already being processed
    lock_key = f"map_lock:{map_id}"
    if redis.get(lock_key):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Map is currently being processed by another request",
        )

    # Lock the map for processing
    redis.set(lock_key, "locked", ex=60)  # 60 second expiry

    # Use map state provider to generate system messages
    messages_response = await get_all_map_messages(map_id, session)
    current_messages = [msg["message_json"] for msg in messages_response["messages"]]

    current_map_description = await get_map_description(
        request,
        map_id,
        session,
        postgis_provider=postgis_provider,
        layer_describer=layer_describer,
        connection_manager=connection_manager,
    )
    description_text = current_map_description.body.decode("utf-8")

    # Get system messages from the provider
    system_messages = await map_state.get_system_messages(
        current_messages, description_text
    )

    async with async_conn("send_map_message.update_messages") as conn:
        # Add any generated system messages to the database
        for system_msg in system_messages:
            system_message = ChatCompletionSystemMessageParam(
                role="system",
                content=system_msg["content"],
            )
            system_message_dict = (
                system_message.model_dump()
                if isinstance(system_message, BaseModel)
                else system_message
            )
            await conn.execute(
                """
                INSERT INTO chat_completion_messages
                (map_id, sender_id, message_json)
                VALUES ($1, $2, $3)
                """,
                map_id,
                user_id,
                json.dumps(system_message_dict),
            )

        # Add user's message to DB
        message_dict = (
            message.model_dump() if isinstance(message, BaseModel) else message
        )
        user_msg_db = await conn.fetchrow(
            """
            INSERT INTO chat_completion_messages
            (map_id, sender_id, message_json)
            VALUES ($1, $2, $3)
            RETURNING id, map_id, sender_id, message_json, created_at
            """,
            map_id,
            user_id,
            json.dumps(message_dict),
        )

    # Start background task
    background_tasks.add_task(
        process_chat_interaction_task,
        request,
        map_id,
        session,
        user_id,
        chat_args,
        map_state,
        system_prompt_provider,
        connection_manager,
    )

    return MessageSendResponse(
        message_id=str(user_msg_db["id"]),
        status="processing_started",
    )


@router.post(
    "/{map_id}/messages/cancel",
    operation_id="cancel_map_message",
    response_class=JSONResponse,
)
async def cancel_map_message(
    request: Request,
    map_id: str,
    session: UserContext = Depends(verify_session_required),
):
    async with async_conn("cancel_map_message") as conn:
        # Authenticate and check map
        map_result = await conn.fetchrow(
            "SELECT owner_uuid FROM user_mundiai_maps WHERE id = $1 AND soft_deleted_at IS NULL",
            map_id,
        )

        if not map_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Map not found"
            )

        if session.get_user_id() != str(map_result["owner_uuid"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        redis.set(f"messages:{map_id}:cancelled", "true", ex=300)  # 5 minute expiry

        return JSONResponse(content={"status": "cancelled"})
