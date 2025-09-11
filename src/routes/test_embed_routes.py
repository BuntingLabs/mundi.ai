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
import os
from unittest.mock import patch


@pytest.mark.anyio
async def test_embed_route_with_no_env_var(auth_client, test_project_with_map):
    project_id = test_project_with_map["project_id"]

    with patch.dict(os.environ, {"MUNDI_EMBED_ALLOWED_ORIGINS": ""}):
        response = await auth_client.get(f"/api/projects/embed/v1/{project_id}.html")
        assert response.status_code == 404


@pytest.mark.anyio
async def test_embed_route_with_empty_env_var(auth_client, test_project_with_map):
    project_id = test_project_with_map["project_id"]

    with patch.dict(os.environ, {"MUNDI_EMBED_ALLOWED_ORIGINS": ""}):
        response = await auth_client.get(f"/api/projects/embed/v1/{project_id}.html")
        assert response.status_code == 404


@pytest.mark.anyio
async def test_embed_route_with_whitespace_only_env_var(
    auth_client, test_project_with_map
):
    project_id = test_project_with_map["project_id"]

    with patch.dict(os.environ, {"MUNDI_EMBED_ALLOWED_ORIGINS": "  ,  "}):
        response = await auth_client.get(f"/api/projects/embed/v1/{project_id}.html")
        assert response.status_code == 404


@pytest.mark.anyio
async def test_embed_route_with_no_origin_header(auth_client, test_project_with_map):
    project_id = test_project_with_map["project_id"]

    with patch.dict(os.environ, {"MUNDI_EMBED_ALLOWED_ORIGINS": "https://example.com"}):
        response = await auth_client.get(f"/api/projects/embed/v1/{project_id}.html")
        assert response.status_code == 404


@pytest.mark.anyio
async def test_embed_route_with_invalid_origin(auth_client, test_project_with_map):
    project_id = test_project_with_map["project_id"]

    with patch.dict(os.environ, {"MUNDI_EMBED_ALLOWED_ORIGINS": "https://example.com"}):
        response = await auth_client.get(
            f"/api/projects/embed/v1/{project_id}.html",
            headers={"origin": "https://malicious.com"},
        )
        assert response.status_code == 404


@pytest.mark.anyio
async def test_embed_route_with_valid_origin(
    auth_client, test_project_with_multiple_origins
):
    project_id = test_project_with_multiple_origins["project_id"]

    with patch.dict(
        os.environ,
        {"MUNDI_EMBED_ALLOWED_ORIGINS": "https://site1.com,https://site2.com"},
    ):
        response = await auth_client.get(
            f"/api/projects/embed/v1/{project_id}.html",
            headers={"origin": "https://site1.com"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        csp_header = response.headers["content-security-policy"]
        # Check key CSP components are present
        assert "frame-ancestors 'self'" in csp_header
        assert "https://site1.com" in csp_header
        assert "https://site2.com" in csp_header
        assert "script-src 'self' 'unsafe-inline' https://unpkg.com" in csp_header
        assert "worker-src 'self' blob:" in csp_header
        assert "style-src 'self' 'unsafe-inline' https://unpkg.com" in csp_header
        assert "connect-src 'self' https://unpkg.com" in csp_header
        assert "img-src 'self' data:" in csp_header
        assert "font-src 'self' https://unpkg.com" in csp_header
        # Ensure at least one tile source is allowed in connect-src and img-src
        assert any(
            domain in csp_header
            for domain in [
                "tile.openstreetmap.org",
                "api.maptiler.com",
                "demotiles.maplibre.org",
            ]
        )
        assert "maplibregl.Map" in response.text
        assert '"sources"' in response.text  # Check that style JSON is inlined


@pytest.mark.anyio
async def test_embed_route_with_valid_referer(
    auth_client, test_project_with_multiple_origins
):
    project_id = test_project_with_multiple_origins["project_id"]

    with patch.dict(os.environ, {"MUNDI_EMBED_ALLOWED_ORIGINS": "https://site1.com"}):
        response = await auth_client.get(
            f"/api/projects/embed/v1/{project_id}.html",
            headers={"referer": "https://site1.com/guides/embedding-maps"},
        )
        assert response.status_code == 200
        csp_header = response.headers["content-security-policy"]
        # Check key CSP components are present
        assert "frame-ancestors 'self'" in csp_header
        assert "https://site1.com" in csp_header
        assert "script-src 'self' 'unsafe-inline' https://unpkg.com" in csp_header
        assert "worker-src 'self' blob:" in csp_header
        assert "style-src 'self' 'unsafe-inline' https://unpkg.com" in csp_header
        assert "connect-src 'self' https://unpkg.com" in csp_header
        assert "img-src 'self' data:" in csp_header
        assert "font-src 'self' https://unpkg.com" in csp_header
        # Ensure at least one tile source is allowed
        assert any(
            domain in csp_header
            for domain in [
                "tile.openstreetmap.org",
                "api.maptiler.com",
                "demotiles.maplibre.org",
            ]
        )


@pytest.mark.anyio
async def test_embed_route_with_invalid_referer(auth_client, test_project_with_map):
    project_id = test_project_with_map["project_id"]

    with patch.dict(
        os.environ, {"MUNDI_EMBED_ALLOWED_ORIGINS": "http://localhost:4321"}
    ):
        response = await auth_client.get(
            f"/api/projects/embed/v1/{project_id}.html",
            headers={"referer": "https://malicious.com/page"},
        )
        assert response.status_code == 404


@pytest.mark.anyio
async def test_embed_route_with_nonexistent_project(auth_client):
    with patch.dict(os.environ, {"MUNDI_EMBED_ALLOWED_ORIGINS": "https://example.com"}):
        response = await auth_client.get(
            "/api/projects/embed/v1/nonexistent.html",
            headers={"origin": "https://example.com"},
        )
        assert response.status_code == 404


@pytest.mark.anyio
async def test_embed_route_headers_with_multiple_origins(
    auth_client, test_project_with_multiple_origins
):
    project_id = test_project_with_multiple_origins["project_id"]

    with patch.dict(
        os.environ,
        {
            "MUNDI_EMBED_ALLOWED_ORIGINS": "https://site1.com, https://site2.com, https://site3.com"
        },
    ):
        response = await auth_client.get(
            f"/api/projects/embed/v1/{project_id}.html",
            headers={"origin": "https://site2.com"},
        )
        assert response.status_code == 200
        csp_header = response.headers["content-security-policy"]
        # Check key CSP components are present
        assert "frame-ancestors 'self'" in csp_header
        assert "https://site1.com" in csp_header
        assert "https://site2.com" in csp_header
        assert "https://site3.com" in csp_header
        assert "script-src 'self' 'unsafe-inline' https://unpkg.com" in csp_header
        assert "worker-src 'self' blob:" in csp_header
        assert "style-src 'self' 'unsafe-inline' https://unpkg.com" in csp_header
        assert "connect-src 'self' https://unpkg.com" in csp_header
        assert "img-src 'self' data:" in csp_header
        assert "font-src 'self' https://unpkg.com" in csp_header
        # Ensure at least one tile source is allowed
        assert any(
            domain in csp_header
            for domain in [
                "tile.openstreetmap.org",
                "api.maptiler.com",
                "demotiles.maplibre.org",
            ]
        )
