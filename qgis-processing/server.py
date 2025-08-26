# Copyright (C) 2025 Bunting Labs, Inc.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import json
import tempfile
import os
import subprocess
import time
from urllib.parse import urlparse
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()


class QGISProcessRequest(BaseModel):
    algorithm_id: str
    qgis_inputs: Dict[str, Any]
    input_urls: Optional[Dict[str, str]] = None
    output_presigned_put_urls: Optional[Dict[str, str]] = None


@app.post("/run_qgis_process")
def run_qgis_process(request: QGISProcessRequest) -> Dict[str, Any]:
    # Validate that input_urls and output_presigned_put_urls don't have overlapping parameter names
    if request.input_urls and request.output_presigned_put_urls:
        overlapping_params = set(request.input_urls.keys()) & set(
            request.output_presigned_put_urls.keys()
        )
        if overlapping_params:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Parameter name conflict",
                    "message": f"The following parameters are specified in both input_urls and output_presigned_put_urls: {list(overlapping_params)}",
                    "overlapping_parameters": list(overlapping_params),
                },
            )

    with tempfile.TemporaryDirectory() as temp_dir:
        start_time = time.time()

        if request.input_urls:
            for param_name, url in request.input_urls.items():
                # Check if this is a regular HTTP/HTTPS URL that needs downloading as a file
                # OGR driver-prefixed URLs (WFS:, ESRIJSON:, /vsicurl/) should be passed directly to QGIS
                if url.startswith(("http://", "https://")):
                    # Traditional file download for regular HTTP/HTTPS URLs
                    parsed = urlparse(url)
                    filename = os.path.basename(parsed.path)
                    if "." not in filename:
                        raise HTTPException(
                            status_code=400,
                            detail={
                                "error": "Invalid Input URL",
                                "message": "Input URL basename must have a file extension",
                            },
                        )

                    local_path = os.path.join(temp_dir, filename)

                    try:
                        with urlopen(url) as response:
                            with open(local_path, "wb") as f:
                                f.write(response.read())
                    except (HTTPError, URLError):
                        raise HTTPException(
                            status_code=400,
                            detail={
                                "error": "Failed to download input file",
                                "message": "Could not download from URL",
                            },
                        )

                    # Update qgis_inputs to use local path
                    request.qgis_inputs[param_name] = local_path
                else:
                    # Pass OGR source strings directly to QGIS without downloading
                    request.qgis_inputs[param_name] = url

        # Also add OUTPUT parameters that are only specified in output_presigned_put_urls
        if request.output_presigned_put_urls:
            for param_name, put_url in request.output_presigned_put_urls.items():
                if param_name not in request.qgis_inputs:
                    parsed_url = urlparse(put_url)
                    url_path = parsed_url.path

                    request.qgis_inputs[param_name] = os.path.join(
                        temp_dir, os.path.basename(url_path)
                    )

        qgis_start_time = time.time()
        result = subprocess.run(
            ["qgis_process", "run", request.algorithm_id, "-"],
            input=json.dumps({"inputs": request.qgis_inputs}),
            capture_output=True,
            text=True,
        )
        qgis_end_time = time.time()
        qgis_execution_time_ms = (qgis_end_time - qgis_start_time) * 1000

        if result.returncode != 0:
            end_time = time.time()
            total_execution_time_ms = (end_time - start_time) * 1000

            error_info = {
                "error": "qgis_process failed",
                "stderr": result.stderr,
                "stdout": result.stdout,
                "returncode": result.returncode,
                "algorithm_id": request.algorithm_id,
                "execution_metadata": {
                    "total_execution_time_ms": total_execution_time_ms,
                    "qgis_execution_time_ms": qgis_execution_time_ms,
                    "start_time": start_time,
                    "end_time": end_time,
                },
            }
            raise HTTPException(status_code=500, detail=error_info)

        # Parse successful result
        qgis_result = json.loads(result.stdout.lstrip("'"))

        # Upload output files if presigned URLs provided
        upload_results = {}
        if request.output_presigned_put_urls:
            for param_name, put_url in request.output_presigned_put_urls.items():
                output_path = None

                if param_name in qgis_result.get("outputs", {}):
                    output_path = qgis_result["outputs"][param_name]
                elif param_name in request.qgis_inputs:
                    output_path = request.qgis_inputs[param_name]

                if output_path and os.path.exists(output_path):
                    try:
                        with open(output_path, "rb") as f:
                            data = f.read()

                        req = Request(
                            put_url,
                            data=data,
                            method="PUT",
                        )
                        with urlopen(req) as response:
                            pass  # Just ensure the request succeeds

                        upload_results[param_name] = {
                            "uploaded": True,
                            "file_size": os.path.getsize(output_path),
                        }
                    except Exception as e:
                        upload_results[param_name] = {
                            "uploaded": False,
                            "error": str(e),
                        }
                else:
                    upload_results[param_name] = {
                        "uploaded": False,
                        "error": f"Output file not found: {output_path}",
                    }

        end_time = time.time()
        total_execution_time_ms = (end_time - start_time) * 1000

        enhanced_result = {
            **qgis_result,
            "execution_metadata": {
                "total_execution_time_ms": total_execution_time_ms,
                "qgis_execution_time_ms": qgis_execution_time_ms,
                "start_time": start_time,
                "end_time": end_time,
                "algorithm_id": request.algorithm_id,
            },
            "upload_results": upload_results,
        }

        return enhanced_result


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
