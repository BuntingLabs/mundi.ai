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


@pytest.mark.anyio
async def test_remote_file_with_pmtiles_generation(auth_client):
    """Test remote file processing with PMTiles generation."""
    remote_url = "https://github.com/BuntingLabs/mundi.ai/raw/aa187476cbbbc03273d303a8ba34eb546a2df1de/test_fixtures/airports.geojson"

    map_response = await auth_client.post(
        "/api/maps/create", json={"name": "Test Map for Remote File"}
    )
    assert map_response.status_code == 200
    map_id = map_response.json()["id"]

    response = await auth_client.post(
        f"/api/maps/{map_id}/layers/remote",
        json={
            "url": remote_url,
            "name": "Test Remote GeoJSON Layer",
            "source_type": "vector",
        },
    )

    if response.status_code != 200:
        print(f"Error response: {response.status_code} - {response.text}")
    assert response.status_code == 200

    layer_id = response.json()["id"]
    layer_type = response.json()["type"]
    assert layer_type == "vector"

    pmtiles_response = await auth_client.get(f"/api/layer/{layer_id}.pmtiles")
    if pmtiles_response.status_code != 200:
        print(
            f"PMTiles request failed: {pmtiles_response.status_code} - {pmtiles_response.text}"
        )
    assert pmtiles_response.status_code == 200
    assert len(pmtiles_response.content) > 0, "PMTiles content should not be empty"

    # PMTiles v3 format starts with 'PMTi' (0x504d5469)
    assert pmtiles_response.content[:4] == b"PMTi", (
        f"Invalid PMTiles file signature: {pmtiles_response.content[:4]}"
    )

    response_data = response.json()
    assert "id" in response_data
    assert "name" in response_data
    assert "type" in response_data
    assert "url" in response_data
    assert response_data["name"] == "Test Remote GeoJSON Layer"

    print(f"Remote file layer created successfully with ID: {layer_id}")
    print(f"PMTiles generated and accessible ({len(pmtiles_response.content)} bytes)")


@pytest.mark.anyio
async def test_google_sheets_with_pmtiles_generation(auth_client):
    """Test Google Sheets processing with PMTiles generation."""
    expected_csv_url = "CSV:/vsicurl/https://docs.google.com/spreadsheets/d/1vsHncOHn0l5uk29zFYG9HvAMHMS1tanXJKKsMCs2hkw/export?format=csv&id=1vsHncOHn0l5uk29zFYG9HvAMHMS1tanXJKKsMCs2hkw&gid=0"

    map_response = await auth_client.post(
        "/api/maps/create", json={"name": "Test Map for Google Sheets"}
    )
    assert map_response.status_code == 200
    map_id = map_response.json()["id"]

    response = await auth_client.post(
        f"/api/maps/{map_id}/layers/remote",
        json={
            "url": expected_csv_url,
            "name": "Test Google Sheets Layer",
            "source_type": "sheets",
            "add_layer_to_map": True,
        },
    )

    if response.status_code != 200:
        print(f"Error response: {response.status_code} - {response.text}")
    assert response.status_code == 200

    response_data = response.json()
    layer_id = response_data["id"]
    layer_type = response_data["type"]
    assert layer_type == "vector"

    pmtiles_response = await auth_client.get(f"/api/layer/{layer_id}.pmtiles")
    assert pmtiles_response.status_code == 200
    assert len(pmtiles_response.content) > 0, "PMTiles content should not be empty"

    # PMTiles v3 format starts with 'PMTi' (0x504d5469)
    assert pmtiles_response.content[:4] == b"PMTi", (
        f"Invalid PMTiles file signature: {pmtiles_response.content[:4]}"
    )

    assert "id" in response_data
    assert "name" in response_data
    assert "type" in response_data
    assert "url" in response_data
    assert response_data["name"] == "Test Google Sheets Layer"

    print(f"Google Sheets layer created successfully with ID: {layer_id}")
    print(f"PMTiles generated and accessible ({len(pmtiles_response.content)} bytes)")


@pytest.mark.anyio
async def test_wfs_with_pmtiles_generation(auth_client):
    """Test WFS processing with PMTiles generation."""
    wfs_url = "https://geo.stat.fi/geoserver/wfs?service=WFS&version=2.0.0&request=GetFeature&typename=vaestoruutu:vaki2021_5km&maxfeatures=10"

    map_response = await auth_client.post(
        "/api/maps/create", json={"name": "Test Map for WFS Layer"}
    )
    assert map_response.status_code == 200
    map_id = map_response.json()["id"]

    response = await auth_client.post(
        f"/api/maps/{map_id}/layers/remote",
        json={
            "url": wfs_url,
            "name": "Test WFS Population Layer",
            "source_type": "vector",
            "add_layer_to_map": True,
        },
    )

    if response.status_code != 200:
        print(f"Error response: {response.status_code} - {response.text}")
        print(f"WFS URL used: {wfs_url}")
    assert response.status_code == 200

    response_data = response.json()
    layer_id = response_data["id"]
    layer_type = response_data["type"]
    assert layer_type == "vector"

    pmtiles_response = await auth_client.get(f"/api/layer/{layer_id}.pmtiles")
    assert pmtiles_response.status_code == 200
    assert len(pmtiles_response.content) > 0, "PMTiles content should not be empty"

    # PMTiles v3 format starts with 'PMTi' (0x504d5469)
    assert pmtiles_response.content[:4] == b"PMTi", (
        f"Invalid PMTiles file signature: {pmtiles_response.content[:4]}"
    )


@pytest.mark.anyio
async def test_send_message_with_all_remote_layers(auth_client):
    """Test /send message functionality with all three types of remote layers attached to a map."""
    from unittest.mock import patch, AsyncMock
    from openai.types.chat import ChatCompletionMessage

    class MockChoice:
        def __init__(self, content: str, tool_calls=None):
            self.message = ChatCompletionMessage(
                content=content, tool_calls=tool_calls, role="assistant"
            )

    class MockResponse:
        def __init__(self, content: str, tool_calls=None):
            self.choices = [MockChoice(content, tool_calls)]

    # Create a map
    map_response = await auth_client.post(
        "/api/maps/create", json={"name": "Test Map for All Remote Layers"}
    )
    assert map_response.status_code == 200
    map_data = map_response.json()
    map_id = map_data["id"]
    project_id = map_data["project_id"]

    print(f"Created map {map_id} in project {project_id}")

    # Add WFS layer
    wfs_url = "https://geo.stat.fi/geoserver/wfs?service=WFS&version=2.0.0&request=GetFeature&typename=vaestoruutu:vaki2021_5km&maxfeatures=10"
    wfs_response = await auth_client.post(
        f"/api/maps/{map_id}/layers/remote",
        json={
            "url": wfs_url,
            "name": "Finland Population WFS",
            "source_type": "vector",
            "add_layer_to_map": True,
        },
    )
    assert wfs_response.status_code == 200
    wfs_data = wfs_response.json()
    wfs_layer_id = wfs_data["id"]
    current_map_id = wfs_data.get(
        "dag_child_map_id", map_id
    )  # Update map_id for chaining
    print(f"Added WFS layer: {wfs_layer_id}, current map: {current_map_id}")

    # Add CSV layer (Google Sheets) - use current_map_id
    csv_url = "CSV:/vsicurl/https://docs.google.com/spreadsheets/d/1vsHncOHn0l5uk29zFYG9HvAMHMS1tanXJKKsMCs2hkw/export?format=csv&id=1vsHncOHn0l5uk29zFYG9HvAMHMS1tanXJKKsMCs2hkw&gid=0"
    csv_response = await auth_client.post(
        f"/api/maps/{current_map_id}/layers/remote",
        json={
            "url": csv_url,
            "name": "Test CSV Data",
            "source_type": "sheets",
            "add_layer_to_map": True,
        },
    )
    if csv_response.status_code != 200:
        print(
            f"CSV layer creation failed: {csv_response.status_code} - {csv_response.text}"
        )
    assert csv_response.status_code == 200
    csv_data = csv_response.json()
    csv_layer_id = csv_data["id"]
    current_map_id = csv_data.get(
        "dag_child_map_id", current_map_id
    )  # Update map_id for chaining
    print(f"Added CSV layer: {csv_layer_id}, current map: {current_map_id}")

    # Add GeoJSON layer - use current_map_id
    geojson_url = "https://raw.githubusercontent.com/holtzy/D3-graph-gallery/master/DATA/world.geojson"
    geojson_response = await auth_client.post(
        f"/api/maps/{current_map_id}/layers/remote",
        json={
            "url": geojson_url,
            "name": "World Countries GeoJSON",
            "source_type": "vector",
            "add_layer_to_map": True,
        },
    )
    assert geojson_response.status_code == 200
    geojson_data = geojson_response.json()
    geojson_layer_id = geojson_data["id"]
    current_map_id = geojson_data.get(
        "dag_child_map_id", current_map_id
    )  # Update map_id for chaining
    print(f"Added GeoJSON layer: {geojson_layer_id}, current map: {current_map_id}")

    # Add ESRI Feature Service layer - use current_map_id
    esri_url = "https://sampleserver6.arcgisonline.com/arcgis/rest/services/PoolPermits/FeatureServer/0/query?f=pjson&resultRecordCount=10"
    esri_response = await auth_client.post(
        f"/api/maps/{current_map_id}/layers/remote",
        json={
            "url": esri_url,
            "name": "Pool Permits ESRI FS",
            "source_type": "vector",
            "add_layer_to_map": True,
        },
    )
    if esri_response.status_code != 200:
        print(
            f"ESRI layer creation failed: {esri_response.status_code} - {esri_response.text}"
        )
    assert esri_response.status_code == 200
    esri_data = esri_response.json()
    esri_layer_id = esri_data["id"]
    final_map_id = esri_data.get("dag_child_map_id", current_map_id)  # Final map_id
    print(f"Added ESRI layer: {esri_layer_id}, final map: {final_map_id}")

    # Create a conversation
    conversation_response = await auth_client.post(
        "/api/conversations",
        json={"project_id": project_id},
    )
    assert conversation_response.status_code == 200
    conversation_id = conversation_response.json()["id"]
    print(f"Created conversation: {conversation_id}")

    # Mock OpenAI responses
    mock_responses = [
        MockResponse(
            "I can see your map contains four different types of remote data layers:\n\n"
            "1. **Finland Population WFS** - A WFS (Web Feature Service) layer with population data from Finland\n"
            "2. **Test CSV Data** - A CSV dataset imported from Google Sheets\n"
            "3. **World Countries GeoJSON** - A GeoJSON layer showing country boundaries\n"
            "4. **USGS Earthquakes ESRI FS** - An ESRI Feature Service layer with earthquake data from USGS\n\n"
            "This is a great example of integrating multiple remote data sources! Each layer type is handled differently by the system - WFS uses direct service calls, CSV data is processed through the sheets interface, GeoJSON is fetched as a standard vector format, and ESRI Feature Services use the ESRI JSON driver.\n\n"
            "What would you like to analyze or visualize with this data?"
        )
    ]

    with patch("src.routes.message_routes.get_openai_client") as mock_get_client:
        mock_client = AsyncMock()
        response_queue = mock_responses[:]
        captured_messages = []

        async def mock_create(*args, **kwargs):
            # Capture the messages sent to OpenAI for inspection
            if "messages" in kwargs:
                captured_messages.extend(kwargs["messages"])
            elif len(args) > 0 and hasattr(args[0], "messages"):
                captured_messages.extend(args[0].messages)
            return response_queue.pop(0)

        mock_client.chat.completions.create = AsyncMock(side_effect=mock_create)
        mock_get_client.return_value = mock_client

        # Send a message about the map - use final_map_id with all layers
        message_response = await auth_client.post(
            f"/api/maps/conversations/{conversation_id}/maps/{final_map_id}/send",
            json={
                "message": {
                    "role": "user",
                    "content": "Can you describe the layers in this map?",
                },
                "selected_feature": None,
            },
        )

        print(f"Message response status: {message_response.status_code}")
        if message_response.status_code != 200:
            print(f"Error response: {message_response.text}")

        assert message_response.status_code == 200
        response_data = message_response.json()

        print(
            f"Assistant response: {response_data.get('content', 'No content')[:200]}..."
        )

        system_messages = [
            msg for msg in captured_messages if msg.get("role") == "system"
        ]

        all_system_content = "\n".join(
            [msg.get("content", "") for msg in system_messages]
        )

        assert "Driver: WFS" in all_system_content
        assert "CRS: EPSG:3067" in all_system_content
        assert "Finland Population WFS" in all_system_content
        assert "Geometry Type: polygon" in all_system_content
        assert (
            "Feature Count: 10359" in all_system_content
            or "Feature Count: 10" in all_system_content
        )
        assert "vaesto" in all_system_content
        assert "kunta" in all_system_content

        assert "Driver: CSV" in all_system_content
        assert "Test CSV Data" in all_system_content
        assert "Geometry Type: point" in all_system_content
        assert "Feature Count: 3" in all_system_content
        assert "San Francisco" in all_system_content
        assert "weather" in all_system_content
        assert "lat" in all_system_content and "long" in all_system_content

        assert "Driver: GeoJSON" in all_system_content
        assert "CRS: EPSG:4326" in all_system_content
        assert "World Countries GeoJSON" in all_system_content
        assert "Geometry Type: multipolygon" in all_system_content
        assert "Feature Count: 177" in all_system_content
        assert "Afghanistan" in all_system_content

        # Test ESRI Feature Service layer description
        assert "Pool Permits" in all_system_content
        assert "Feature Count: 983" in all_system_content
        assert "Dataset Bounds: -117.46"
        assert "apn" in all_system_content
        assert "Driver: ESRIJSON" in all_system_content


@pytest.mark.anyio
async def test_esri_feature_service_with_pmtiles_generation(auth_client):
    """Test ESRI Feature Service processing with PMTiles generation."""
    # Use the pool permits URL that works reliably
    esri_url = "https://sampleserver6.arcgisonline.com/arcgis/rest/services/PoolPermits/FeatureServer/0/query?resultRecordCount=10&f=pjson"

    map_response = await auth_client.post(
        "/api/maps/create", json={"name": "Test Map for ESRI Feature Service"}
    )
    assert map_response.status_code == 200
    map_id = map_response.json()["id"]

    response = await auth_client.post(
        f"/api/maps/{map_id}/layers/remote",
        json={
            "url": esri_url,
            "name": "Test ESRI Feature Service Layer",
            "source_type": "vector",
        },
    )

    if response.status_code != 200:
        print(f"Error response: {response.status_code} - {response.text}")
    assert response.status_code == 200

    layer_id = response.json()["id"]
    layer_type = response.json()["type"]
    assert layer_type == "vector"

    # Test that PMTiles were generated
    pmtiles_response = await auth_client.get(f"/api/layer/{layer_id}.pmtiles")
    if pmtiles_response.status_code != 200:
        print(
            f"PMTiles request failed: {pmtiles_response.status_code} - {pmtiles_response.text}"
        )
    assert pmtiles_response.status_code == 200
    assert len(pmtiles_response.content) > 0, "PMTiles content should not be empty"

    # PMTiles v3 format starts with 'PMTi' (0x504d5469)
    assert pmtiles_response.content[:4] == b"PMTi", (
        f"Invalid PMTiles file signature: {pmtiles_response.content[:4]}"
    )

    print(f"ESRI Feature Service test passed. Layer ID: {layer_id}")
    print(
        f"PMTiles generated successfully, size: {len(pmtiles_response.content)} bytes"
    )


@pytest.mark.anyio
async def test_esri_url_with_frontend_transformation(auth_client):
    """Test ESRI Feature Service with frontend-style URL transformation."""
    # Use pool permits URL which is known to work reliably
    esri_url_with_limit = "https://sampleserver6.arcgisonline.com/arcgis/rest/services/PoolPermits/FeatureServer/0/query?f=pjson&resultRecordCount=10"

    map_response = await auth_client.post(
        "/api/maps/create", json={"name": "Test Map for ESRI with Limit"}
    )
    assert map_response.status_code == 200
    map_id = map_response.json()["id"]

    response = await auth_client.post(
        f"/api/maps/{map_id}/layers/remote",
        json={
            "url": esri_url_with_limit,
            "name": "Pool Permits Test",
            "source_type": "vector",
        },
    )

    print(f"Response status: {response.status_code}")
    if response.status_code != 200:
        print(f"Response text: {response.text}")

    assert response.status_code == 200, "URL with resultRecordCount should work"

    layer_id = response.json()["id"]

    # Test PMTiles generation
    pmtiles_response = await auth_client.get(f"/api/layer/{layer_id}.pmtiles")
    assert pmtiles_response.status_code == 200
    assert len(pmtiles_response.content) > 0

    print(f"✅ Pool permits ESRI service works. Layer ID: {layer_id}")
    print(
        f"✅ PMTiles generated successfully, size: {len(pmtiles_response.content)} bytes"
    )
