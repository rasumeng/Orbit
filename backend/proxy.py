"""Local-only proxy for Orbit's Lambda API, invoked with local AWS credentials."""

import json
import os
import asyncio
import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, ProfileNotFound
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
FUNCTION_NAME = os.getenv("ORBIT_FUNCTION_NAME", "OrbitBackend")
ALLOWED_PATHS = {"/health", "/spaces", "/spaces/open", "/spaces/me", "/items", "/items/import", "/projects", "/projects/join"}
lambda_client = boto3.client("lambda", region_name=AWS_REGION)

app = FastAPI(title="Orbit local AWS proxy", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["content-type", "x-orbit-access-code"],
)


async def forward(request: Request, path: str) -> Response:
    body = await request.body()
    try:
        credentials = boto3.Session(region_name=AWS_REGION).get_credentials()
        if credentials is None:
            raise NoCredentialsError()
        event = {
            "requestContext": {"http": {"method": request.method}},
            "rawPath": path,
            "headers": {
                "content-type": request.headers.get("content-type", "application/json"),
                "x-orbit-access-code": request.headers.get("x-orbit-access-code", ""),
            },
            "body": body.decode("utf-8") if body else None,
        }
        invocation = await asyncio.to_thread(
            lambda_client.invoke,
            FunctionName=FUNCTION_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(event).encode("utf-8"),
        )
        payload = json.loads(invocation["Payload"].read() or b"{}")
    except (NoCredentialsError, ProfileNotFound):
        return Response(
            content=json.dumps({"error": "AWS credentials are not configured for the local proxy"}),
            status_code=503,
            media_type="application/json",
        )
    except (BotoCoreError, ClientError, ValueError) as exc:
        print("Lambda invocation failed:", type(exc).__name__)
        return Response(content=json.dumps({"error": "Could not reach the Orbit Lambda function"}), status_code=502, media_type="application/json")
    if invocation.get("FunctionError") or not isinstance(payload, dict):
        return Response(content=json.dumps({"error": "Orbit Lambda function failed"}), status_code=502, media_type="application/json")
    response_body = payload.get("body", "{}")
    response_headers = payload.get("headers") or {}
    return Response(content=response_body, status_code=payload.get("statusCode", 502), media_type=response_headers.get("content-type", "application/json"))


@app.api_route("/{path:path}", methods=["GET", "POST", "PATCH"])
async def proxy(path: str, request: Request) -> Response:
    normalized = f"/{path}" if path else "/"
    if normalized.startswith("/items/") and request.method == "PATCH":
        return await forward(request, normalized)
    if normalized in ALLOWED_PATHS:
        return await forward(request, normalized)
    return Response(content=json.dumps({"error": "Route not found"}), status_code=404, media_type="application/json")

