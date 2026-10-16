"""Local-only proxy for Orbit's IAM-protected Lambda Function URL."""

import json
import os
from typing import Any

import boto3
import httpx
from botocore.awsrequest import AWSRequest
from botocore.auth import SigV4Auth
from botocore.exceptions import NoCredentialsError
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

LAMBDA_URL = os.getenv("ORBIT_LAMBDA_URL", "").rstrip("/")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_SERVICE = "lambda"
ALLOWED_PATHS = {"/health", "/items"}

app = FastAPI(title="Orbit local AWS proxy", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["content-type"],
)


def signed_request(method: str, url: str, body: bytes, content_type: str | None) -> dict[str, Any]:
    session = boto3.Session(region_name=AWS_REGION)
    credentials = session.get_credentials()
    if credentials is None:
        raise NoCredentialsError()
    frozen = credentials.get_frozen_credentials()
    headers = {"host": url.split("/", 3)[2]}
    if content_type:
        headers["content-type"] = content_type
    aws_request = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(frozen, AWS_SERVICE, AWS_REGION).add_auth(aws_request)
    return dict(aws_request.headers.items())


async def forward(request: Request, path: str) -> Response:
    if not LAMBDA_URL:
        return Response(
            content=json.dumps({"error": "ORBIT_LAMBDA_URL is not configured for the local proxy"}),
            status_code=503,
            media_type="application/json",
        )
    body = await request.body()
    try:
        headers = signed_request(request.method, f"{LAMBDA_URL}{path}", body, request.headers.get("content-type"))
    except NoCredentialsError:
        return Response(
            content=json.dumps({"error": "AWS credentials are not configured for the local proxy"}),
            status_code=503,
            media_type="application/json",
        )
    async with httpx.AsyncClient(timeout=15.0) as client:
        upstream = await client.request(request.method, f"{LAMBDA_URL}{path}", content=body, headers=headers)
    return Response(content=upstream.content, status_code=upstream.status_code, media_type=upstream.headers.get("content-type", "application/json"))


@app.api_route("/{path:path}", methods=["GET", "POST", "PATCH"])
async def proxy(path: str, request: Request) -> Response:
    normalized = f"/{path}" if path else "/"
    if normalized.startswith("/items/") and request.method == "PATCH":
        return await forward(request, normalized)
    if normalized in ALLOWED_PATHS:
        return await forward(request, normalized)
    return Response(content=json.dumps({"error": "Route not found"}), status_code=404, media_type="application/json")

