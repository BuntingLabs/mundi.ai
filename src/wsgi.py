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

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.routes import (
    postgres_routes,
    project_routes,
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


app.include_router(
    postgres_routes.router,
    prefix="/api/maps",
    tags=["Maps"],
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


app.mount("/assets", StaticFiles(directory="frontendts/dist/assets"), name="spa-assets")


@app.get("/favicon-light.svg")
async def get_favicon_light_svg():
    return FileResponse("frontendts/dist/favicon-light.svg")


@app.get("/favicon-dark.svg")
async def get_favicon_dark_svg():
    return FileResponse("frontendts/dist/favicon-dark.svg")


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
