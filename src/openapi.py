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

import json
import re
from pathlib import Path
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from src.wsgi import app

app.openapi_url = "/openapi.json"


_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def _canon(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def prune_redundant_titles(node):
    # remove 'title' fields that are just humanized versions of the property/parameter names.
    if isinstance(node, dict):
        # case 1: object schema with properties
        if isinstance(node.get("properties"), dict):
            for prop_name, prop_schema in list(node["properties"].items()):
                # recurse first (handles nested objects/arrays)
                prune_redundant_titles(prop_schema)
                title = prop_schema.get("title")
                if isinstance(title, str) and _canon(title) == _canon(prop_name):
                    prop_schema.pop("title", None)

        # case 2: parameter object { name, in, schema: { title: ... } }
        if {"name", "in", "schema"} <= node.keys() and isinstance(node["schema"], dict):
            title = node["schema"].get("title")
            if isinstance(title, str) and _canon(title) == _canon(str(node["name"])):
                node["schema"].pop("title", None)
            prune_redundant_titles(node["schema"])

        # recurse generically through other fields (items, allOf, etc. too)
        for k, v in list(node.items()):
            if isinstance(v, (dict, list)) and k not in ("properties", "schema"):
                prune_redundant_titles(v)

    elif isinstance(node, list):
        for item in node:
            prune_redundant_titles(item)


def _clean_param_list(params):
    """
    Remove bogus/empty query params (e.g., name=='request' or empty schema).
    Returns a filtered list.
    """
    if not isinstance(params, list):
        return params
    cleaned = []
    for p in params:
        if not isinstance(p, dict):
            continue
        # Keep $ref unless it clearly references "request"
        if "$ref" in p:
            if p["$ref"].split("/")[-1].lower() == "request":
                continue
            cleaned.append(p)
            continue
        name = str(p.get("name", "")).lower()
        loc = p.get("in")
        schema = p.get("schema")
        is_bogus_request = loc == "query" and name == "request"
        is_empty_query = loc == "query" and (
            not isinstance(schema, dict) or len(schema) == 0
        )
        if is_bogus_request or is_empty_query:
            continue
        cleaned.append(p)
    return cleaned


def _drop_empty_query_params(spec: dict):
    """Strip bad query params and remove empty `parameters` arrays."""
    comp = spec.get("components", {})
    if isinstance(comp.get("parameters"), dict):
        for key, p in list(comp["parameters"].items()):
            if (
                isinstance(p, dict)
                and p.get("in") == "query"
                and (str(p.get("name", "")).lower() == "request" or not p.get("schema"))
            ):
                del comp["parameters"][key]

    for path_item in spec.get("paths", {}).values():
        if isinstance(path_item.get("parameters"), list):
            path_item["parameters"] = _clean_param_list(path_item["parameters"])
            if not path_item["parameters"]:
                path_item.pop("parameters", None)
        for method, op in list(path_item.items()):
            if method not in _HTTP_METHODS or not isinstance(op, dict):
                continue
            if isinstance(op.get("parameters"), list):
                op["parameters"] = _clean_param_list(op["parameters"])
                if not op["parameters"]:
                    op.pop("parameters", None)


def custom_openapi():
    keep_names = {
        "create_map",
        "upload_layer_to_map",
        "set_layer_style",
        "render_map_to_png",
        "delete_project",
        "update_layer",
        "update_map",
    }
    selected_routes = [
        r
        for r in app.router.routes
        if isinstance(r, APIRoute) and r.operation_id in keep_names
    ]

    openapi_schema = get_openapi(
        title="Mundi.ai Developer API",
        version="0.0.1",
        summary="Mundi.ai has a developer API for creating, editing, and sharing maps and map data.",
        description="""
Mundi is a customizable, open source web GIS and can be operated via API just like it can be used as a web app. You can [programatically create maps](/developer-api/operations/create_map/), [upload geospatial data](/developer-api/operations/upload_layer_to_map/) (vectors, raster, point clouds), and share map links or embed maps in other web applications.

Mundi's API is both available as a [hosted cloud service](https://mundi.ai) or
[a self-hosted set of Docker images](https://github.com/buntinglabs/mundi.ai), open source under the AGPLv3 license.

To get started, create an account at [Mundi.ai](https://app.mundi.ai) and create a new API key [here](https://app.mundi.ai/settings/api-keys).
When sending requests, set the `Authorization` header to `Bearer YOUR_API_KEY`. API keys start with `sk-...`. Never share your API keys.

```py
# 1. create a new map project
created_map = httpx.post(
    "https://app.mundi.ai/api/maps/create",
    json={"title": "US political boundaries"},
    headers={"Authorization": f"Bearer {os.environ["MUNDI_API_KEY"]}"},
).json()
map_id, project_id = created_map["id"], created_map["project_id"]

# 2. upload a GeoJSON file as a layer on that map
with open("counties.geojson", "rb") as f:
    upload = httpx.post(
        f"https://app.mundi.ai/api/maps/{map_id}/layers",
        files={"file": ("counties.geojson", f, "application/geo+json")},
        data={"layer_name": "US Counties", "add_layer_to_map": True},
        headers={"Authorization": f"Bearer {os.environ["MUNDI_API_KEY"]}"},
    ).json()

# 3. link to view the map with the uploaded layer
print(f"https://app.mundi.ai/project/{project_id}/{map_id}")
```
""",
        routes=selected_routes,
        terms_of_service="https://buntinglabs.com/legal/terms",
        contact={
            "name": "Bunting Labs",
            "url": "https://buntinglabs.com",
        },
    )

    prune_redundant_titles(openapi_schema)
    _drop_empty_query_params(openapi_schema)

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

if __name__ == "__main__":
    # Generate the OpenAPI schema
    schema = custom_openapi()

    # Define the target path
    target_path = Path("docs/src/schema/openapi.json")

    # Create directories if they don't exist
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Write the schema to the file
    with open(target_path, "w") as f:
        json.dump(schema, f)

    print(f"OpenAPI schema written to {target_path}")
