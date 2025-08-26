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
import pytest
from src.symbology.verify import verify_full_style_json_str, StyleValidationError


@pytest.mark.anyio
async def test_verify_valid_style_json():
    with open(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "test_fixtures",
            "maplibre_valid_style.json",
        ),
        "r",
    ) as f:
        style_json_str = f.read()

    is_valid = await verify_full_style_json_str(style_json_str)
    assert is_valid, "Valid style was incorrectly marked as invalid"


@pytest.mark.anyio
async def test_verify_invalid_style_json():
    with open(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "test_fixtures",
            "maplibre_invalid_style.json",
        ),
        "r",
    ) as f:
        style_json_str = f.read()

    try:
        result = await verify_full_style_json_str(style_json_str)
        assert not result, "Invalid style was incorrectly marked as valid"
    except StyleValidationError as e:
        assert 'source "crimea" not found' in str(e), (
            "Expected error message not found in exception"
        )
