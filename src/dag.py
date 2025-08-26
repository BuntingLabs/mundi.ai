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

import secrets
from pydantic import BaseModel, Field
from enum import Enum


class DAGEditOperationResponse(BaseModel):
    dag_child_map_id: str = Field(
        description="The ID of the new map created that contains the changes. Use this ID for further operations on the modified map."
    )
    dag_parent_map_id: str = Field(
        description="The ID of the original map which was copied to create the new map."
    )


def generate_id(length=12, prefix=""):
    """Generate a unique ID for the map or layer.

    Using characters [1-9A-HJ-NP-Za-km-z] (excluding 0, O, I, l)
    to avoid ambiguity in IDs.
    """
    assert len(prefix) in [0, 1], "Prefix must be at most 1 character"

    valid_chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    result = "".join(secrets.choice(valid_chars) for _ in range(length - len(prefix)))
    return prefix + result


class ForkReason(Enum):
    """Reason for forking a map"""

    USER_EDIT = "user_edit"
    AI_EDIT = "ai_edit"
