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

import os
import base64
import json
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi_proxy_lib.fastapi.app import reverse_http_app, reverse_ws_app
import httpx

from src.routes import (
    postgres_routes,
    project_routes,
    room_routes,
    message_routes,
    websocket,
    conversation_routes,
)
from src.routes.postgres_routes import basemap_router
from src.routes.layer_router import layer_router
from src.routes.attribute_table import attribute_table_router
# from fastapi_mcp import FastApiMCP


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run database migrations on startup"""
    from src.database.migrate import run_migrations

    await run_migrations()
    yield
    # Cleanup code here if needed


app = FastAPI(
    title="Mundi.ai",
    description="Open source, AI native GIS software",
    version="0.0.1",
    # Don't show OpenAPI spec, docs, redoc
    openapi_url=None,
    lifespan=lifespan,
)


@app.exception_handler(httpx.RemoteProtocolError)
async def handle_driftdb_error(request: Request, exc: httpx.RemoteProtocolError):
    if not request.url.path.startswith("/room/"):
        raise exc

    return JSONResponse(
        status_code=404,
        content={"detail": "Room not found, likely expired"},
    )


app.include_router(
    postgres_routes.router,
    prefix="/api/maps",
    tags=["Maps"],
)
app.include_router(
    room_routes.router,
    prefix="/api/maps",
    tags=["Collaboration"],
)
app.include_router(
    message_routes.router,
    prefix="/api/maps",
    tags=["Messages"],
)
app.include_router(
    websocket.router,
    prefix="/api/maps",
    tags=["WebSocket"],
)
app.include_router(
    layer_router,
    prefix="/api",
    tags=["Layers"],
)
app.include_router(
    attribute_table_router,
    prefix="/api",
    tags=["Attribute Tables"],
)
app.include_router(
    project_routes.project_router,
    prefix="/api/projects",
    tags=["Maps"],
)
app.include_router(
    basemap_router,
    prefix="/api/basemaps",
    tags=["Basemaps"],
)
app.include_router(
    conversation_routes.router,
    prefix="/api",
    tags=["Conversations"],
)


# Create a combined proxy router for DriftDB that handles both HTTP and WebSocket
# Use a WebSocket-capable proxy for the /room routes
room_ws_app = reverse_ws_app(base_url="ws://driftdb:8080/room/")
# Mount it as a sub-application
app.mount("/room/", room_ws_app)

# Use HTTP proxy for other DriftDB paths
drift_app = reverse_http_app(base_url="http://driftdb:8080/")
# Mount it as a sub-application
app.mount("/drift/", drift_app)


# TODO: this isn't useful right now. But we should work on it in the future
# mcp = FastApiMCP(
#     app,
#     name="Mundi.ai MCP",
#     description="GIS as an MCP",
#     exclude_operations=[
#         "upload_layer_to_map",
#         "view_layer_as_geojson",
#         "view_layer_as_pmtiles",
#         "view_layer_as_cog_tif",
#         "remove_layer_from_map",
#         "view_map_html",
#         "get_map_stylejson",
#         "describe_layer",
#     ],
# )
# mcp.mount()


# First mount specific static assets to ensure they're properly served
app.mount("/assets", StaticFiles(directory="frontendts/dist/assets"), name="spa-assets")


@app.post("/supertokens/session/refresh")
async def mock_session_refresh(request: Request):
    # it's simpler for self hosters to not have to log in, and there's a big
    # gap between a simple, self hostable app and a secure, multi tenant, public
    # facing software
    if os.environ.get("MUNDI_AUTH_MODE") == "edit":
        # Create fake refresh response
        expiry = int(time.time() * 1000) + 3600 * 1000  # 1 hour
        front_token = base64.b64encode(
            json.dumps({"uid": "demo", "ate": expiry, "up": {}}).encode()
        ).decode()

        id_refresh = str(uuid.uuid4())
        anti_csrf = str(uuid.uuid4())
        access_tok = f"dummyAccess.{uuid.uuid4()}"
        refresh_tok = f"dummyRefresh.{uuid.uuid4()}"

        response = JSONResponse(status_code=200, content={})

        # Headers
        response.headers["front-token"] = front_token
        response.headers["id-refresh-token"] = id_refresh
        response.headers["anti-csrf"] = anti_csrf
        response.headers["access-control-expose-headers"] = (
            "front-token, id-refresh-token, anti-csrf"
        )
        response.headers["access-control-allow-credentials"] = "true"

        # Cookies
        response.set_cookie("sAccessToken", access_tok, httponly=True)
        response.set_cookie("sRefreshToken", refresh_tok, httponly=True)
        response.set_cookie("sIdRefreshToken", id_refresh, httponly=True)

        return response


@app.exception_handler(StarletteHTTPException)
async def spa_server(request: Request, exc: StarletteHTTPException):
    # Don't handle API 404s - let them bubble up as real 404s
    if (
        request.url.path.startswith("/api/")
        or request.url.path.startswith("/supertokens/")
        or request.url.path.startswith("/mcp")
    ):
        # Return standard 404 response for API routes and MCP routes
        return JSONResponse(
            status_code=exc.status_code, content={"detail": str(exc.detail)}
        )

    # For all other routes, return the SPA's index.html
    return FileResponse("frontendts/dist/index.html")
