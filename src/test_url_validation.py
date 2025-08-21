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
from fastapi import HTTPException
from src.routes.postgres_routes import validate_remote_url


def test_validate_remote_url_blocks_private_ips():
    """Test that private IP addresses are blocked"""

    # Test loopback addresses
    with pytest.raises(HTTPException) as exc_info:
        validate_remote_url("http://127.0.0.1/data.geojson", "vector")
    assert "Access to private IP addresses is not allowed: 127.0.0.1" == str(
        exc_info.value.detail
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_remote_url("http://localhost/data.geojson", "vector")
    assert "is not allowed" in str(exc_info.value.detail)


def test_validate_remote_url_blocks_cloud_metadata():
    """Test that cloud metadata endpoints are blocked"""

    # Test AWS metadata endpoint
    with pytest.raises(HTTPException) as exc_info:
        validate_remote_url("http://169.254.169.254/latest/meta-data/", "vector")
    assert "is not allowed" in str(exc_info.value.detail)

    # Test ECS task metadata endpoint
    with pytest.raises(HTTPException) as exc_info:
        validate_remote_url("http://169.254.170.2/v4/credentials", "vector")
    assert "is not allowed" in str(exc_info.value.detail)


def test_validate_remote_url_requires_http_prefix():
    """Test that URLs must start with http:// or https://"""

    with pytest.raises(HTTPException) as exc_info:
        validate_remote_url("ftp://example.com/data.geojson", "vector")
    assert "URL must start with http:// or https://" in str(exc_info.value.detail)

    with pytest.raises(HTTPException) as exc_info:
        validate_remote_url("file:///etc/passwd", "vector")
    assert "URL must start with http:// or https://" in str(exc_info.value.detail)


def test_validate_remote_url_csv_requires_prefix():
    """Test that Google Sheets URLs must have CSV:/vsicurl/ prefix"""

    with pytest.raises(HTTPException) as exc_info:
        validate_remote_url(
            "https://docs.google.com/spreadsheets/d/123/export", "sheets"
        )
    assert "Google Sheets URLs must use CSV:/vsicurl/https://... format" in str(
        exc_info.value.detail
    )

    # Valid CSV URL should pass validation (assuming external host is resolvable)
    try:
        result = validate_remote_url(
            "CSV:/vsicurl/https://docs.google.com/spreadsheets/d/123/export", "sheets"
        )
        assert (
            result == "CSV:/vsicurl/https://docs.google.com/spreadsheets/d/123/export"
        )
    except HTTPException as e:
        # May fail due to DNS resolution, but should not fail on format validation
        assert "format" not in str(e.detail)


def test_validate_remote_url_allows_valid_urls():
    """Test that valid external URLs are allowed"""

    # These may fail due to DNS resolution in test environment, but should pass format validation
    valid_urls = [
        "https://example.com/data.geojson",
        "http://data.example.org/layer.shp",
        "https://api.example.net/wfs?service=WFS&request=GetFeature",
    ]

    for url in valid_urls:
        try:
            result = validate_remote_url(url, "vector")
            assert result == url
        except HTTPException as e:
            # May fail due to DNS resolution, but should not fail on format validation
            assert "format" not in str(e.detail).lower()
            assert "must start with http" not in str(e.detail)


def test_validate_remote_url_invalid_hostname():
    """Test that URLs with invalid hostnames are rejected"""

    with pytest.raises(HTTPException) as exc_info:
        validate_remote_url("http:///data.geojson", "vector")
    assert "Invalid URL: missing hostname" in str(exc_info.value.detail)
